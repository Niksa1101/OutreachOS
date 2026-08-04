"""The workspace lock.

Q83: `.oos-lock` carrying `{pid, hostname, boot_id, started_at}`. A stale or
foreign-host lock offers "Take over".

Two things about it are easy to get wrong.

**Staleness is PID *plus* process start time.** A dead PID's number gets
recycled, so "that PID is alive" does not mean "that process is ours". Comparing
the start time as well is what distinguishes our crashed instance from whatever
now happens to own the number.

**The lock is never swept at boot** (a late correction, and it reverses the
obvious implementation). Sweeping before acquisition would delete a lock that
may belong to a live instance on another machine — the network-share case the
lock exists for — and silently bypass the foreign-host warning. Sweeping after
acquisition could only ever delete our own lock, making it a no-op. **The
staleness check *is* the cleanup path.**

Q38's Job Object kill means there is no clean shutdown when Tauri is killed, so
stale locks are the normal case rather than the exception. This code runs often
enough that it needs to be the well-tested path, not the fallback.
"""

import json
import logging
import os
import socket
from dataclasses import asdict, dataclass
from pathlib import Path

from outreachos_backend.core.timeutil import utcnow_iso

__all__ = ["LockHolder", "LockState", "acquire", "release"]

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LockHolder:
    pid: int
    hostname: str
    boot_id: str
    started_at: str
    process_started_at: float | None = None
    """Process creation time, seconds since epoch.

    The half of the staleness check that stops a recycled PID from looking
    alive. `None` when it could not be read, which degrades the check to
    PID-only rather than failing it.
    """


@dataclass(frozen=True)
class LockState:
    acquired: bool
    holder: LockHolder | None = None
    foreign_host: bool = False
    """True when the lock names a different machine. The user gets a warning
    and "Take over" rather than a refusal, because we genuinely cannot tell
    from here whether that instance is alive."""


def _process_start_time(pid: int) -> float | None:
    """Creation time of `pid`, or `None` if it cannot be determined."""
    if pid <= 0:
        return None

    try:
        import ctypes
        import ctypes.wintypes
    except ImportError:  # pragma: no cover — non-Windows
        return None

    if os.name != "nt":  # pragma: no cover — Windows is the only target
        return None

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None

    try:
        creation = ctypes.wintypes.FILETIME()
        exit_time = ctypes.wintypes.FILETIME()
        kernel_time = ctypes.wintypes.FILETIME()
        user_time = ctypes.wintypes.FILETIME()

        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        )
        if not ok:
            return None

        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        # FILETIME is 100ns intervals since 1601-01-01; 11644473600 is the
        # offset to the Unix epoch.
        return ticks / 10_000_000 - 11_644_473_600
    finally:
        kernel32.CloseHandle(handle)


def _is_alive(holder: LockHolder) -> bool:
    """Is the process named by this lock still the one that took it?"""
    start = _process_start_time(holder.pid)

    if start is None:
        # No such process, or no permission to ask. Either way it is not ours
        # to worry about.
        return False

    if holder.process_started_at is None:
        # A lock written before we recorded start times, or on a platform where
        # it could not be read. PID-only is weaker but is the best available.
        return True

    # A second of tolerance: the value is derived from a 100ns clock but is
    # round-tripped through JSON, and an exact float compare would report every
    # live process as dead.
    return abs(start - holder.process_started_at) < 1.0


def read(lock_file: Path) -> LockHolder | None:
    try:
        payload = json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A missing lock and an unreadable one lead to the same place: there is
        # no holder we can identify, so the lock cannot be honoured.
        return None

    try:
        return LockHolder(
            pid=int(payload["pid"]),
            hostname=str(payload["hostname"]),
            boot_id=str(payload["boot_id"]),
            started_at=str(payload["started_at"]),
            process_started_at=(
                float(payload["process_started_at"])
                if payload.get("process_started_at") is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None


def acquire(lock_file: Path, boot_id: str, *, take_over: bool = False) -> LockState:
    """Take the workspace lock, or report who holds it.

    `take_over=True` is the user having pressed the button. It is the only way
    past a live-looking lock, and it is deliberately a decision rather than a
    heuristic — we cannot tell a live instance on another machine from a
    crashed one.
    """
    existing = read(lock_file)

    if existing is not None and not take_over:
        foreign = existing.hostname != socket.gethostname()

        if foreign:
            log.warning(
                "the workspace is locked by %s on another machine (%s)",
                existing.pid,
                existing.hostname,
            )
            return LockState(acquired=False, holder=existing, foreign_host=True)

        if _is_alive(existing):
            log.warning("the workspace is locked by a running process (pid %s)", existing.pid)
            return LockState(acquired=False, holder=existing)

        # Stale. This is the normal case, not the exception — see the module
        # docstring on the Job Object kill path.
        log.info("replacing a stale lock from pid %s", existing.pid)

    holder = LockHolder(
        pid=os.getpid(),
        hostname=socket.gethostname(),
        boot_id=boot_id,
        started_at=utcnow_iso(),
        process_started_at=_process_start_time(os.getpid()),
    )

    lock_file.write_text(json.dumps(asdict(holder), indent=2), encoding="utf-8")
    return LockState(acquired=True, holder=holder)


def release(lock_file: Path, boot_id: str) -> None:
    """Remove the lock, but only if it is still ours.

    Q118 puts this late in the shutdown sequence, after the server has stopped.
    The ownership check matters because a "Take over" from another instance may
    have replaced our lock while we were still running — deleting it then would
    unlock a workspace somebody else is actively using.
    """
    holder = read(lock_file)

    if holder is None:
        return

    if holder.boot_id != boot_id:
        log.warning("not releasing the lock: it belongs to boot %s", holder.boot_id)
        return

    try:
        lock_file.unlink(missing_ok=True)
    except OSError:
        log.warning("could not remove %s", lock_file, exc_info=True)
