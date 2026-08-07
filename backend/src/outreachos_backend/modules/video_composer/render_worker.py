"""The video-composer-specific claim/run pair for ``rendering.queue.pool.WorkerPool``.

Two job types share one queue and one worker loop (DB.md §3.3). Both pass
through a common ``waiting -> preparing`` claim; from there ``alpha_prepare``
moves through ``rendering`` and ``video_render`` through ``encoding`` — the
two type-specific stages of the six states the ticket requires — before
landing on ``completed`` or ``failed``.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from outreachos_backend.core.enums import AssetRole, JobStatus, JobType
from outreachos_backend.core.events import EventBus
from outreachos_backend.core.settings_service import resolve_encoder_override, resolve_quality
from outreachos_backend.core.timeutil import utcnow_iso
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.models import Campaign, MediaAsset, RenderJob
from outreachos_backend.modules.video_composer.service import (
    batch_event_payload,
    job_event_payload,
)
from outreachos_backend.rendering.alpha import build_alpha_clip
from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.cache import CacheLayout
from outreachos_backend.rendering.capabilities import select_encoder
from outreachos_backend.rendering.config import (
    OverlayConfig,
    QualityPreset,
    RenderBatchConfig,
    ScreenRecordingJob,
    TalkingHeadConfig,
    upgrade_overlay_config,
)
from outreachos_backend.rendering.errors import (
    RenderError,
    RenderProcessError,
    cap_stderr,
    format_command,
)
from outreachos_backend.rendering.process import clear_cancel, is_cancelled
from outreachos_backend.rendering.render import render_one

__all__ = ["build_run_job", "claim_next_job"]

log = logging.getLogger(__name__)

#: Progress ticks: integer-percent dedupe plus a wall-clock floor so a fast
#: encode cannot flood the event stream (and the client's query cache).
_PROGRESS_MIN_INTERVAL_S = 0.5


def claim_next_job(session: Session) -> str | None:
    """Atomic claim: next eligible ``waiting`` job, in queue order.

    Eligible means no dependency, a dependency that has already completed, or a
    dependency row that no longer exists — ``depends_on_job_id`` is deliberately
    not a foreign key (see the model), so orphans are reachable via cancel,
    campaign delete, and later export pruning. No orphan should wedge the queue.
    The claim itself is a compare-and-swap ``UPDATE ... WHERE status = 'waiting'``:
    if another worker won the race between the read and the write, ``rowcount``
    is 0 and the caller tries again on its next tick.
    """
    completed_dep = select(RenderJob.id).where(RenderJob.status == JobStatus.COMPLETED.value)
    existing_ids = select(RenderJob.id)
    candidate_id = session.scalar(
        select(RenderJob.id)
        .where(
            RenderJob.status == JobStatus.WAITING.value,
            (RenderJob.depends_on_job_id.is_(None))
            | (RenderJob.depends_on_job_id.in_(completed_dep))
            | (RenderJob.depends_on_job_id.notin_(existing_ids)),
        )
        .order_by(RenderJob.queue_position, RenderJob.id)
        .limit(1)
    )
    if candidate_id is None:
        return None

    result = cast(
        CursorResult[Any],
        session.execute(
            update(RenderJob)
            .where(RenderJob.id == candidate_id, RenderJob.status == JobStatus.WAITING.value)
            .values(
                status=JobStatus.PREPARING.value,
                started_at=utcnow_iso(),
                attempts=RenderJob.attempts + 1,
            )
        ),
    )
    session.commit()
    if result.rowcount != 1:
        return None
    return candidate_id


def build_run_job(
    *,
    binaries: Binaries,
    workspace: WorkspaceLayout,
    event_bus: EventBus,
) -> Callable[[Session, str], None]:
    """Bind the worker pool's fixed ``run_job(session, id)`` signature to the
    request-scoped collaborators (ffmpeg binaries, workspace, event bus) that
    only exist once the app has booted.
    """

    def run_job(session: Session, job_id: str) -> None:
        job = session.get(RenderJob, job_id)
        if job is None:
            clear_cancel(job_id)
            return
        campaign = session.get(Campaign, job.campaign_id)
        if campaign is None:
            # The campaign was deleted after this job was claimed (delete
            # cascades the row, so this is only reachable via a race with an
            # in-flight delete). Nothing left to report against.
            clear_cancel(job_id)
            return

        try:
            if job.job_type == JobType.ALPHA_PREPARE.value:
                _run_alpha_prepare(session, job, campaign, binaries, workspace, event_bus)
            else:
                _run_video_render(session, job, campaign, binaries, workspace, event_bus)
        except Exception as exc:
            if _abandon_if_cancelled(session, job_id):
                return
            log.exception("render worker: unhandled error running job %s", job_id)
            _fail_job(session, job, campaign, event_bus, message=f"Unexpected error: {exc}")
        finally:
            clear_cancel(job_id)

    return run_job


def _abandon_if_cancelled(session: Session, job_id: str) -> bool:
    """True when cancel already removed the row — do not write a failed status."""
    if not is_cancelled(job_id):
        return False
    session.expire_all()
    return session.get(RenderJob, job_id) is None


def _overlay_config(campaign: Campaign) -> OverlayConfig:
    return upgrade_overlay_config(
        json.loads(campaign.overlay_config), from_version=campaign.overlay_schema_version
    )


def _talking_head_config(talking_head: MediaAsset) -> TalkingHeadConfig:
    assert talking_head.trim_start_ms is not None
    assert talking_head.trim_end_ms is not None
    assert talking_head.focal_x is not None
    assert talking_head.focal_y is not None
    return TalkingHeadConfig(
        source_path=Path(talking_head.source_path),
        trim_start_ms=talking_head.trim_start_ms,
        trim_end_ms=talking_head.trim_end_ms,
        focal_x=talking_head.focal_x,
        focal_y=talking_head.focal_y,
    )


def _quality_for(session: Session, campaign: Campaign) -> QualityPreset:
    return resolve_quality(session, quality_override=campaign.quality_override)


def _encoder_for(session: Session) -> str | None:
    return resolve_encoder_override(session)


def _publish_status(
    event_bus: EventBus,
    session: Session,
    campaign_name: str,
    job: RenderJob,
) -> None:
    """Status transition: job row + batch rollup (sidebar badge / header)."""
    event_bus.render_job_changed(job_event_payload(campaign_name, job))
    event_bus.batch_progress_changed(batch_event_payload(session))


def _publish_progress(
    event_bus: EventBus,
    campaign_name: str,
    job: RenderJob,
) -> None:
    """Progress tick: job row only — batch is recomputed on status changes."""
    event_bus.render_job_changed(job_event_payload(campaign_name, job))


def _fail_job(
    session: Session,
    job: RenderJob,
    campaign: Campaign,
    event_bus: EventBus,
    *,
    message: str,
    details: str | None = None,
    command: list[str] | None = None,
) -> None:
    """Persist a failed job (ticket 20 / ADR-0011).

    Full stderr is written to the rolling workspace log first; the DB row stores
    the capped copy plus a pasteable command. A failure here never stops the
    worker loop — the pool claims the next waiting job on its next tick.
    """
    if _abandon_if_cancelled(session, job.id):
        return

    if details:
        log.error(
            "render job %s (%s) failed: %s\n%s",
            job.id,
            job.job_type,
            message,
            details,
        )
    else:
        log.error("render job %s (%s) failed: %s", job.id, job.job_type, message)

    job.status = JobStatus.FAILED.value
    job.error_message = message
    job.error_details = cap_stderr(details) if details else None
    job.ffmpeg_command = format_command(command) if command else None
    job.finished_at = utcnow_iso()
    session.commit()
    _publish_status(event_bus, session, campaign.name, job)


def _details_from_render_error(exc: RenderError) -> str:
    stderr = getattr(exc, "stderr", "") or ""
    if stderr:
        return f"{exc}\n{stderr}".rstrip()
    return str(exc)


def _plain_message_for_process_error(*, job_type: str) -> str:
    if job_type == JobType.ALPHA_PREPARE.value:
        return "FFmpeg failed while preparing the overlay."
    return "FFmpeg failed while encoding this video."


def _fail_from_render_error(
    session: Session,
    job: RenderJob,
    campaign: Campaign,
    event_bus: EventBus,
    exc: RenderError,
) -> None:
    if isinstance(exc, RenderProcessError):
        _fail_job(
            session,
            job,
            campaign,
            event_bus,
            message=_plain_message_for_process_error(job_type=job.job_type),
            details=_details_from_render_error(exc),
            command=exc.command,
        )
        return
    _fail_job(
        session,
        job,
        campaign,
        event_bus,
        message=str(exc) or "The render failed.",
        details=_details_from_render_error(exc),
        command=getattr(exc, "command", None),
    )


def _cascade_fail_dependents(
    session: Session, alpha_job: RenderJob, campaign: Campaign, event_bus: EventBus
) -> None:
    """PRD §6.4: a failed ``alpha_prepare`` fails every job waiting on it.

    Only ``waiting`` dependents — one already claimed by another (impossible
    today at concurrency 1, but the claim is CAS-safe for when it isn't) is
    left for its own worker to resolve rather than raced here.
    """
    dependents = session.scalars(
        select(RenderJob).where(
            RenderJob.depends_on_job_id == alpha_job.id,
            RenderJob.status == JobStatus.WAITING.value,
        )
    ).all()
    for dependent in dependents:
        dependent.status = JobStatus.FAILED.value
        dependent.error_message = "The alpha clip failed to build; this video was not attempted."
        # Surface the alpha job's plain summary as technical detail — dependents
        # never ran FFmpeg, so there is no stderr/command of their own.
        dependent.error_details = alpha_job.error_message
        dependent.finished_at = utcnow_iso()
        log.error(
            "render job %s (%s) failed: %s (cascaded from alpha_prepare %s)",
            dependent.id,
            dependent.job_type,
            dependent.error_message,
            alpha_job.id,
        )
    session.commit()
    for dependent in dependents:
        _publish_status(event_bus, session, campaign.name, dependent)


def _run_alpha_prepare(
    session: Session,
    job: RenderJob,
    campaign: Campaign,
    binaries: Binaries,
    workspace: WorkspaceLayout,
    event_bus: EventBus,
) -> None:
    talking_head = session.scalar(
        select(MediaAsset).where(
            MediaAsset.campaign_id == campaign.id,
            MediaAsset.role == AssetRole.TALKING_HEAD.value,
        )
    )
    if talking_head is None:
        _fail_job(session, job, campaign, event_bus, message="No talking head is assigned.")
        _cascade_fail_dependents(session, job, campaign, event_bus)
        return

    config = RenderBatchConfig(
        talking_head=_talking_head_config(talking_head),
        overlay=_overlay_config(campaign),
        recordings=[],
        quality=_quality_for(session, campaign),
        encoder=_encoder_for(session),
        owner_ref=campaign.id,
        owner_kind="campaign",
    )
    layout = CacheLayout(root=workspace.cache)

    job.status = JobStatus.RENDERING.value
    session.commit()
    _publish_status(event_bus, session, campaign.name, job)

    if is_cancelled(job.id):
        return

    try:
        result = build_alpha_clip(binaries, config, layout, job_id=job.id)
    except RenderError as exc:
        _fail_from_render_error(session, job, campaign, event_bus, exc)
        if not is_cancelled(job.id):
            _cascade_fail_dependents(session, job, campaign, event_bus)
        return

    if _abandon_if_cancelled(session, job.id):
        return

    campaign.alpha_cache_key = result.alpha_key
    campaign.alpha_cache_path = result.clip_path.relative_to(workspace.root).as_posix()
    job.status = JobStatus.COMPLETED.value
    job.progress_pct = 100.0
    job.finished_at = utcnow_iso()
    session.commit()
    _publish_status(event_bus, session, campaign.name, job)


def _run_video_render(
    session: Session,
    job: RenderJob,
    campaign: Campaign,
    binaries: Binaries,
    workspace: WorkspaceLayout,
    event_bus: EventBus,
) -> None:
    asset = session.get(MediaAsset, job.asset_id) if job.asset_id else None
    if asset is None:
        _fail_job(
            session,
            job,
            campaign,
            event_bus,
            message="The source recording no longer exists.",
        )
        return

    talking_head = session.scalar(
        select(MediaAsset).where(
            MediaAsset.campaign_id == campaign.id,
            MediaAsset.role == AssetRole.TALKING_HEAD.value,
        )
    )
    if talking_head is None:
        _fail_job(session, job, campaign, event_bus, message="No talking head is assigned.")
        return

    output_basename = job.output_filename[:-4] if job.output_filename else asset.output_basename
    config = RenderBatchConfig(
        talking_head=_talking_head_config(talking_head),
        overlay=_overlay_config(campaign),
        recordings=[
            ScreenRecordingJob(
                source_path=Path(asset.source_path),
                output_basename=output_basename or asset.id,
            )
        ],
        quality=_quality_for(session, campaign),
        encoder=_encoder_for(session),
        owner_ref=campaign.id,
        owner_kind="campaign",
    )
    layout = CacheLayout(root=workspace.cache)

    try:
        # Reuses the campaign's alpha clip via the same content-addressed
        # cache `alpha_prepare` just populated (or that was already warm) —
        # this is a cache hit, not a rebuild. No job_id: a cancel during the
        # cache-hit probe must not kill an unrelated shared encode.
        alpha = build_alpha_clip(binaries, config, layout)
    except RenderError as exc:
        _fail_from_render_error(session, job, campaign, event_bus, exc)
        return

    if is_cancelled(job.id):
        return

    job.status = JobStatus.ENCODING.value
    session.commit()
    _publish_status(event_bus, session, campaign.name, job)

    out_dir = workspace.outputs / campaign.id
    encoder = select_encoder(binaries, config.encoder)

    last_pct = -1
    last_publish_at = 0.0

    def on_progress(_basename: str, pct: float) -> None:
        nonlocal last_pct, last_publish_at
        if is_cancelled(job.id):
            return
        pct_int = int(pct)
        if pct_int == last_pct:
            return
        now = time.monotonic()
        is_terminal = pct_int >= 100
        if not is_terminal and (now - last_publish_at) < _PROGRESS_MIN_INTERVAL_S:
            return
        last_pct = pct_int
        last_publish_at = now
        job.progress_pct = float(pct_int)
        session.commit()
        _publish_progress(event_bus, campaign.name, job)

    result = render_one(
        binaries,
        config,
        alpha,
        config.recordings[0],
        out_dir,
        encoder=encoder,
        on_progress=on_progress,
        job_id=job.id,
    )

    if _abandon_if_cancelled(session, job.id):
        return

    if not result.ok:
        _fail_job(
            session,
            job,
            campaign,
            event_bus,
            message="FFmpeg failed while encoding this video.",
            details=result.error,
            command=result.command,
        )
        return

    assert result.output_path is not None
    now = utcnow_iso()
    asset.last_rendered_at = now
    asset.last_rendered_cache_key = alpha.alpha_key
    job.output_path = result.output_path.relative_to(workspace.root).as_posix()
    job.output_filename = result.output_path.name
    job.status = JobStatus.COMPLETED.value
    job.progress_pct = 100.0
    job.finished_at = now
    session.commit()
    _publish_status(event_bus, session, campaign.name, job)
