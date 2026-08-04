"""The workspace lock.

Q83, and the late correction that reverses the obvious implementation: **the
lock is never swept at boot.** Its staleness check *is* its cleanup path.

Q38's Job Object kill means there is no clean shutdown when Tauri is killed
from Task Manager, so a stale lock is the normal case rather than the
exception. This path runs often enough that it needs to be the well-tested one.
"""

import json
import os
import socket

from outreachos_backend.core import lock
from outreachos_backend.core.workspace import WorkspaceLayout


def write_lock(layout: WorkspaceLayout, **overrides: object) -> None:
    payload: dict[str, object] = {
        "pid": 999_999,
        "hostname": socket.gethostname(),
        "boot_id": "someone-else",
        "started_at": "2020-01-01T00:00:00.000Z",
        "process_started_at": None,
    }
    payload.update(overrides)
    layout.lock_file.write_text(json.dumps(payload), encoding="utf-8")


def test_an_unlocked_workspace_is_acquired(tmp_workspace: WorkspaceLayout) -> None:
    state = lock.acquire(tmp_workspace.lock_file, "boot-1")

    assert state.acquired
    assert tmp_workspace.lock_file.exists()

    holder = lock.read(tmp_workspace.lock_file)
    assert holder is not None
    assert holder.pid == os.getpid()
    assert holder.boot_id == "boot-1"


def test_a_live_lock_from_this_machine_is_refused(tmp_workspace: WorkspaceLayout) -> None:
    # Our own PID is unambiguously alive, and its recorded start time matches.
    lock.acquire(tmp_workspace.lock_file, "boot-1")

    state = lock.acquire(tmp_workspace.lock_file, "boot-2")

    assert not state.acquired
    assert state.holder is not None
    assert state.holder.boot_id == "boot-1"


def test_a_stale_lock_is_replaced(tmp_workspace: WorkspaceLayout) -> None:
    # The normal case after a Job Object kill, not the exception.
    write_lock(tmp_workspace, pid=999_999)

    state = lock.acquire(tmp_workspace.lock_file, "boot-2")

    assert state.acquired
    holder = lock.read(tmp_workspace.lock_file)
    assert holder is not None
    assert holder.boot_id == "boot-2"


def test_a_recycled_pid_does_not_look_alive(tmp_workspace: WorkspaceLayout) -> None:
    # Q83: "a dead PID's number gets recycled, so 'PID is alive' must also mean
    # 'that process is ours'". Our own PID with somebody else's start time is
    # exactly that collision.
    write_lock(tmp_workspace, pid=os.getpid(), process_started_at=1.0)

    state = lock.acquire(tmp_workspace.lock_file, "boot-2")

    assert state.acquired, "a recycled PID must not hold the workspace hostage"


def test_a_matching_start_time_does_hold_the_lock(tmp_workspace: WorkspaceLayout) -> None:
    # The other side of the same check — the guard must not be so loose that
    # every lock reads as stale.
    real_start = lock._process_start_time(os.getpid())
    write_lock(tmp_workspace, pid=os.getpid(), process_started_at=real_start)

    assert not lock.acquire(tmp_workspace.lock_file, "boot-2").acquired


def test_a_foreign_host_lock_is_reported_rather_than_replaced(
    tmp_workspace: WorkspaceLayout,
) -> None:
    # The network-share case the lock exists for. We cannot tell from here
    # whether that instance is alive, so the user decides.
    write_lock(tmp_workspace, hostname="some-other-machine", pid=os.getpid())

    state = lock.acquire(tmp_workspace.lock_file, "boot-2")

    assert not state.acquired
    assert state.foreign_host


def test_take_over_claims_a_foreign_lock(tmp_workspace: WorkspaceLayout) -> None:
    write_lock(tmp_workspace, hostname="some-other-machine")

    state = lock.acquire(tmp_workspace.lock_file, "boot-2", take_over=True)

    assert state.acquired
    holder = lock.read(tmp_workspace.lock_file)
    assert holder is not None
    assert holder.hostname == socket.gethostname()


def test_an_unreadable_lock_does_not_block_the_workspace(
    tmp_workspace: WorkspaceLayout,
) -> None:
    # A truncated write, or a file somebody edited. There is no holder we can
    # identify, so there is no lock to honour — the alternative is a workspace
    # nobody can ever open again.
    tmp_workspace.lock_file.write_text("{not json", encoding="utf-8")

    assert lock.acquire(tmp_workspace.lock_file, "boot-2").acquired


def test_release_removes_our_own_lock(tmp_workspace: WorkspaceLayout) -> None:
    lock.acquire(tmp_workspace.lock_file, "boot-1")
    lock.release(tmp_workspace.lock_file, "boot-1")

    assert not tmp_workspace.lock_file.exists()


def test_release_leaves_somebody_elses_lock_alone(tmp_workspace: WorkspaceLayout) -> None:
    # Reachable: another instance may have taken over while we were shutting
    # down. Deleting its lock would unlock a workspace it is actively using.
    lock.acquire(tmp_workspace.lock_file, "boot-1")
    lock.acquire(tmp_workspace.lock_file, "boot-2", take_over=True)

    lock.release(tmp_workspace.lock_file, "boot-1")

    holder = lock.read(tmp_workspace.lock_file)
    assert holder is not None
    assert holder.boot_id == "boot-2"


def test_releasing_a_missing_lock_is_not_an_error(tmp_workspace: WorkspaceLayout) -> None:
    lock.release(tmp_workspace.lock_file, "boot-1")
