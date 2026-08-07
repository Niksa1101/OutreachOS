"""Batch-level progress and ETA for the global render queue (ticket 18).

Per-job percentages already stream from FFmpeg. This module rolls those up into
a single batch view and estimates remaining time from **observed** video-render
durations — never a fixed per-job guess — so the ETA stays quiet until there is
enough completed work to trust.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Protocol

from outreachos_backend.core.enums import JobStatus, JobType
from outreachos_backend.modules.video_composer.schemas import BatchProgress

__all__ = ["MIN_ETA_SAMPLES", "JobTiming", "compute_batch_progress"]

#: Completed ``video_render`` durations required before an ETA is shown.
#: One sample is enough to be a number; two keeps the first (often cold-cache)
#: outlier from dominating the estimate.
MIN_ETA_SAMPLES = 2


class JobTiming(Protocol):
    status: str
    job_type: str
    progress_pct: float
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class _Sample:
    seconds: float


def compute_batch_progress(jobs: Sequence[JobTiming]) -> BatchProgress:
    """Roll a queue snapshot into batch counts, progress, and optional ETA."""
    total = len(jobs)
    completed = 0
    failed = 0
    waiting = 0
    active = 0
    fractional_done = 0.0
    remaining_work = 0.0
    samples: list[_Sample] = []

    for job in jobs:
        status = job.status
        if status == JobStatus.COMPLETED.value:
            completed += 1
            fractional_done += 1.0
            sample = _duration_sample(job)
            if sample is not None:
                samples.append(sample)
        elif status == JobStatus.FAILED.value:
            failed += 1
            fractional_done += 1.0
        elif status == JobStatus.WAITING.value:
            waiting += 1
            remaining_work += 1.0
        elif status in (
            JobStatus.PREPARING.value,
            JobStatus.RENDERING.value,
            JobStatus.ENCODING.value,
        ):
            active += 1
            pct = max(0.0, min(100.0, float(job.progress_pct))) / 100.0
            fractional_done += pct
            remaining_work += max(0.0, 1.0 - pct)
        else:
            # Unknown status — treat as remaining so the badge cannot hide work.
            waiting += 1
            remaining_work += 1.0

    progress_pct = 0.0 if total == 0 else (fractional_done / total) * 100.0
    active_job_count = waiting + active
    eta_seconds = _eta_seconds(samples, remaining_work, total=total)

    return BatchProgress(
        total=total,
        completed=completed,
        failed=failed,
        active=active,
        waiting=waiting,
        active_job_count=active_job_count,
        progress_pct=round(progress_pct, 1),
        eta_seconds=eta_seconds,
    )


def _duration_sample(job: JobTiming) -> _Sample | None:
    """A throughput sample from one finished video render.

    Alpha-prepare is excluded: it runs once per cold campaign and its duration
    is a poor predictor of per-video encode time. Using it early in a batch is
    exactly the "wild number" the ticket forbids.
    """
    if job.job_type != JobType.VIDEO_RENDER.value:
        return None
    if not job.started_at or not job.finished_at:
        return None
    start = _parse_iso(job.started_at)
    end = _parse_iso(job.finished_at)
    if start is None or end is None:
        return None
    seconds = (end - start).total_seconds()
    if seconds <= 0:
        return None
    return _Sample(seconds=seconds)


def _eta_seconds(samples: list[_Sample], remaining_work: float, *, total: int) -> int | None:
    if total == 0:
        return None
    if remaining_work <= 0:
        # Nothing left — report done even when we never gathered samples
        # (e.g. a batch that only ever had failed/cancelled work).
        return 0
    if len(samples) < MIN_ETA_SAMPLES:
        return None
    # Median resists a single slow/fast outlier better than the mean; throughput
    # is then jobs-per-second = 1 / typical_seconds.
    typical = median(sample.seconds for sample in samples)
    if typical <= 0:
        return None
    return max(0, round(remaining_work * typical))


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
