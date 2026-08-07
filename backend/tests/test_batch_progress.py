"""Ticket 18: batch rollup, throughput ETA, and graceful early degradation."""

from __future__ import annotations

from dataclasses import dataclass

from outreachos_backend.core.enums import JobStatus, JobType
from outreachos_backend.modules.video_composer.batch_progress import (
    MIN_ETA_SAMPLES,
    compute_batch_progress,
)


@dataclass
class FakeJob:
    status: str
    job_type: str = JobType.VIDEO_RENDER.value
    progress_pct: float = 0.0
    started_at: str | None = None
    finished_at: str | None = None


def test_empty_queue_is_idle() -> None:
    batch = compute_batch_progress([])
    assert batch.total == 0
    assert batch.active_job_count == 0
    assert batch.progress_pct == 0.0
    assert batch.eta_seconds is None


def test_counts_reflect_completed_active_and_waiting() -> None:
    jobs = [
        FakeJob(status=JobStatus.COMPLETED.value, progress_pct=100.0),
        FakeJob(status=JobStatus.FAILED.value, progress_pct=40.0),
        FakeJob(status=JobStatus.ENCODING.value, progress_pct=50.0),
        FakeJob(status=JobStatus.WAITING.value),
        FakeJob(status=JobStatus.WAITING.value),
    ]
    batch = compute_batch_progress(jobs)

    assert batch.total == 5
    assert batch.completed == 1
    assert batch.failed == 1
    assert batch.active == 1
    assert batch.waiting == 2
    assert batch.active_job_count == 3
    # 1 completed + 1 failed + 0.5 in-flight = 2.5 / 5
    assert batch.progress_pct == 50.0


def test_eta_is_null_until_enough_video_render_samples() -> None:
    # One finished video is not enough — avoids a wild first-job guess.
    jobs = [
        FakeJob(
            status=JobStatus.COMPLETED.value,
            progress_pct=100.0,
            started_at="2026-08-07T10:00:00.000Z",
            finished_at="2026-08-07T10:00:10.000Z",
        ),
        FakeJob(status=JobStatus.WAITING.value),
    ]
    assert compute_batch_progress(jobs).eta_seconds is None
    assert MIN_ETA_SAMPLES == 2


def test_alpha_prepare_duration_does_not_seed_eta() -> None:
    # Alpha is once-per-campaign and a poor predictor of encode time.
    jobs = [
        FakeJob(
            status=JobStatus.COMPLETED.value,
            job_type=JobType.ALPHA_PREPARE.value,
            progress_pct=100.0,
            started_at="2026-08-07T10:00:00.000Z",
            finished_at="2026-08-07T10:05:00.000Z",
        ),
        FakeJob(
            status=JobStatus.COMPLETED.value,
            job_type=JobType.ALPHA_PREPARE.value,
            progress_pct=100.0,
            started_at="2026-08-07T10:05:00.000Z",
            finished_at="2026-08-07T10:10:00.000Z",
        ),
        FakeJob(status=JobStatus.WAITING.value),
    ]
    assert compute_batch_progress(jobs).eta_seconds is None


def test_eta_uses_measured_video_render_throughput() -> None:
    jobs = [
        FakeJob(
            status=JobStatus.COMPLETED.value,
            progress_pct=100.0,
            started_at="2026-08-07T10:00:00.000Z",
            finished_at="2026-08-07T10:00:10.000Z",
        ),
        FakeJob(
            status=JobStatus.COMPLETED.value,
            progress_pct=100.0,
            started_at="2026-08-07T10:00:10.000Z",
            finished_at="2026-08-07T10:00:20.000Z",
        ),
        FakeJob(status=JobStatus.ENCODING.value, progress_pct=50.0),
        FakeJob(status=JobStatus.WAITING.value),
        FakeJob(status=JobStatus.WAITING.value),
    ]
    batch = compute_batch_progress(jobs)
    # Median duration 10s; remaining work = 0.5 + 1 + 1 = 2.5 → 25s.
    assert batch.eta_seconds == 25


def test_idle_queue_with_only_terminal_jobs_hides_badge_count() -> None:
    jobs = [
        FakeJob(status=JobStatus.COMPLETED.value, progress_pct=100.0),
        FakeJob(status=JobStatus.FAILED.value),
    ]
    batch = compute_batch_progress(jobs)
    assert batch.active_job_count == 0
    assert batch.progress_pct == 100.0
    assert batch.eta_seconds == 0
