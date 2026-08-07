"""Generic worker pool: N background threads pulling and executing jobs.

Ticket 15's requirement is a real pool abstraction, not a loop hardcoded to one
worker — ``concurrency`` is a constructor parameter, and ``video_composer``'s
wiring in ``__main__.py`` is what pins it to 1 for V1.

``claim_next`` must be a single atomic transaction against ``core/db.py``'s
``Database.session_factory`` (select the next eligible row, flip its status,
commit) so that SQLite's WAL-mode writer serialization is what prevents two
threads from claiming the same row, not application-level locking. It returns
an identifier rather than the ORM row itself: the row was loaded on a session
that closes before ``run_job`` runs, so a returned instance would be detached.
``run_job`` re-fetches by id on its own fresh session instead.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Protocol

__all__ = ["WorkerPool"]

log = logging.getLogger(__name__)


class _SessionLike(Protocol):
    def close(self) -> None: ...


class WorkerPool[T, SessionT: _SessionLike]:
    """Drives ``concurrency`` background threads against a claim/run pair."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], SessionT],
        claim_next: Callable[[SessionT], T | None],
        run_job: Callable[[SessionT, T], None],
        concurrency: int = 1,
        poll_interval_s: float = 5.0,
        name: str = "worker",
    ) -> None:
        self._session_factory = session_factory
        self._claim_next = claim_next
        self._run_job = run_job
        self._concurrency = max(1, concurrency)
        self._poll_interval_s = poll_interval_s
        self._name = name
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._show_resume_prompt = False
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._threads:
            return
        for index in range(self._concurrency):
            thread = threading.Thread(target=self._loop, name=f"{self._name}-{index}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def wake(self) -> None:
        """Nudge idle workers to check for new work immediately.

        Called after an enqueue commits, so a newly queued job starts within
        the same tick rather than waiting out ``poll_interval_s``. While the
        pool is paused the nudge only wakes the wait — no claim happens until
        ``resume``.
        """
        self._wake.set()

    def pause(self, *, show_resume_prompt: bool = False) -> None:
        """Stop claiming new work. An in-flight job is left to finish.

        Ticket 19 owns the user-facing Pause control; ticket 22 uses this at
        boot after crash recovery so relaunch does not silently restart the
        batch. ``show_resume_prompt`` arms the UI banner until ``resume``.
        """
        self._show_resume_prompt = show_resume_prompt
        self._paused.set()

    def resume(self) -> None:
        """Clear a pause and wake idle workers to claim again."""
        self._show_resume_prompt = False
        self._paused.clear()
        self.wake()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def show_resume_prompt(self) -> bool:
        return self._show_resume_prompt

    def stop(self, *, join_timeout_s: float = 5.0) -> None:
        """Stop pulling new work and wait for threads to exit.

        Does not interrupt a job already running — a thread mid-``run_job``
        finishes that call before it notices ``_stop`` on its next loop.
        """
        self._stop.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout=join_timeout_s)
        self._threads.clear()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._paused.is_set():
                self._wake.wait(timeout=self._poll_interval_s)
                self._wake.clear()
                continue
            claimed = self._claim_one()
            if claimed is None:
                self._wake.wait(timeout=self._poll_interval_s)
                self._wake.clear()
                continue
            self._wake.clear()
            self._run_one(claimed)

    def _claim_one(self) -> T | None:
        session = self._session_factory()
        try:
            return self._claim_next(session)
        except Exception:
            log.exception("%s: failed to claim next job", self._name)
            return None
        finally:
            session.close()

    def _run_one(self, claimed: T) -> None:
        session = self._session_factory()
        try:
            self._run_job(session, claimed)
        except Exception:
            log.exception("%s: job runner raised", self._name)
        finally:
            session.close()
