"""Generic ``WorkerPool`` mechanics â€” claim/run/wake/stop â€” with fakes.

No database and no ffmpeg here; ``test_render_worker.py`` covers the
video-composer-specific claim query and job execution against a real DB.
"""

from __future__ import annotations

import threading
import time

from outreachos_backend.rendering.queue.pool import WorkerPool


class _FakeSession:
    def close(self) -> None:
        pass


def _session_factory() -> _FakeSession:
    return _FakeSession()


def test_start_claims_and_runs_a_single_queued_item() -> None:
    queue = ["job-1"]
    ran: list[str] = []
    done = threading.Event()

    def claim_next(_session: _FakeSession) -> str | None:
        return queue.pop(0) if queue else None

    def run_job(_session: _FakeSession, item: str) -> None:
        ran.append(item)
        done.set()

    pool: WorkerPool[str, _FakeSession] = WorkerPool(
        session_factory=_session_factory,
        claim_next=claim_next,
        run_job=run_job,
        concurrency=1,
        poll_interval_s=0.05,
    )
    pool.start()
    try:
        assert done.wait(timeout=2.0)
        assert ran == ["job-1"]
    finally:
        pool.stop(join_timeout_s=1.0)


def test_wake_processes_a_newly_enqueued_item_without_waiting_a_full_poll_interval() -> None:
    queue: list[str] = []
    ran: list[str] = []
    done = threading.Event()

    def claim_next(_session: _FakeSession) -> str | None:
        return queue.pop(0) if queue else None

    def run_job(_session: _FakeSession, item: str) -> None:
        ran.append(item)
        done.set()

    pool: WorkerPool[str, _FakeSession] = WorkerPool(
        session_factory=_session_factory,
        claim_next=claim_next,
        run_job=run_job,
        concurrency=1,
        # A long poll interval: if `wake()` did nothing, the assertion below
        # would time out well before the loop polls again on its own.
        poll_interval_s=30.0,
    )
    pool.start()
    try:
        time.sleep(0.1)  # let the pool reach its idle wait
        queue.append("job-2")
        pool.wake()
        assert done.wait(timeout=2.0)
        assert ran == ["job-2"]
    finally:
        pool.stop(join_timeout_s=1.0)


def test_concurrency_is_configurable_not_hardcoded() -> None:
    queue = [f"job-{i}" for i in range(4)]
    lock = threading.Lock()
    ran: list[str] = []
    all_done = threading.Event()

    def claim_next(_session: _FakeSession) -> str | None:
        with lock:
            return queue.pop(0) if queue else None

    def run_job(_session: _FakeSession, item: str) -> None:
        time.sleep(0.05)
        with lock:
            ran.append(item)
            if len(ran) == 4:
                all_done.set()

    pool: WorkerPool[str, _FakeSession] = WorkerPool(
        session_factory=_session_factory,
        claim_next=claim_next,
        run_job=run_job,
        concurrency=4,
        poll_interval_s=0.05,
    )
    pool.start()
    try:
        assert all_done.wait(timeout=2.0)
        assert sorted(ran) == sorted(f"job-{i}" for i in range(4))
    finally:
        pool.stop(join_timeout_s=1.0)


def test_stop_prevents_further_claims() -> None:
    queue = ["job-1"]
    ran: list[str] = []
    started = threading.Event()

    def claim_next(_session: _FakeSession) -> str | None:
        started.set()
        return None

    def run_job(_session: _FakeSession, item: str) -> None:
        ran.append(item)

    pool: WorkerPool[str, _FakeSession] = WorkerPool(
        session_factory=_session_factory,
        claim_next=claim_next,
        run_job=run_job,
        concurrency=1,
        poll_interval_s=0.05,
    )
    pool.start()
    assert started.wait(timeout=2.0)
    pool.stop(join_timeout_s=1.0)

    queue.append("late-job")
    pool.wake()
    time.sleep(0.2)
    assert ran == []


def test_pause_blocks_claims_until_resume() -> None:
    queue = ["job-1", "job-2"]
    ran: list[str] = []
    first_done = threading.Event()
    second_done = threading.Event()

    def claim_next(_session: _FakeSession) -> str | None:
        return queue.pop(0) if queue else None

    def run_job(_session: _FakeSession, item: str) -> None:
        ran.append(item)
        if item == "job-1":
            first_done.set()
        else:
            second_done.set()

    pool: WorkerPool[str, _FakeSession] = WorkerPool(
        session_factory=_session_factory,
        claim_next=claim_next,
        run_job=run_job,
        concurrency=1,
        poll_interval_s=0.05,
    )
    pool.pause(show_resume_prompt=True)
    pool.start()
    try:
        assert pool.paused
        assert pool.show_resume_prompt
        pool.wake()
        time.sleep(0.2)
        assert ran == []

        pool.resume()
        assert first_done.wait(timeout=2.0)
        assert second_done.wait(timeout=2.0)
        assert ran == ["job-1", "job-2"]
        assert not pool.paused
        assert not pool.show_resume_prompt
    finally:
        pool.stop(join_timeout_s=1.0)
