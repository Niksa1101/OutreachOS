"""Ticket 16: alpha-prepare as its own pinned queue row.

Covers cold vs warm enqueue, job dependencies, cascade failure on alpha
errors, cache invalidation on overlay/trim/focal changes, and a multi-video
benchmark proving the alpha cache saves time on warm batches.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.enums import AssetRole, JobStatus, JobType, ProbeStatus
from outreachos_backend.core.events import EventBus
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer import render_worker
from outreachos_backend.modules.video_composer.models import Campaign, MediaAsset, RenderJob
from outreachos_backend.modules.video_composer.service import (
    generate_videos,
    update_overlay_config,
    update_talking_head_trim,
)
from outreachos_backend.rendering.binaries import Binaries, resolve_binaries
from outreachos_backend.rendering.config import OverlayConfig
from outreachos_backend.rendering.errors import RenderError
from outreachos_backend.rendering.process import run_tool

REPO_ROOT = Path(__file__).resolve().parents[2]
FFMPEG_DIR = REPO_ROOT / "vendor" / "ffmpeg"


@pytest.fixture(scope="session")
def ffmpeg_dir() -> Path:
    if not (FFMPEG_DIR / "ffmpeg.exe").is_file():
        pytest.skip("vendor/ffmpeg not present — run scripts/fetch-ffmpeg.ps1")
    return FFMPEG_DIR


@pytest.fixture(scope="session")
def binaries(ffmpeg_dir: Path) -> Binaries:
    return resolve_binaries(ffmpeg_dir)


@pytest.fixture
def session(tmp_workspace: WorkspaceLayout) -> Generator[Session, None, None]:
    database = Database(tmp_workspace.database)
    outcome = migrate.run_migrations(database.engine, database.path)
    assert outcome.ok, outcome.detail
    migrate.heal_app_settings(database.engine)
    db_session = database.session_factory()
    try:
        yield db_session
    finally:
        db_session.close()
        database.dispose()


def _make_video(binaries: Binaries, path: Path, *, duration: int = 2) -> None:
    args = [
        str(binaries.ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration}:size=1280x720:rate=30",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={duration}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(path),
    ]
    run_tool(args, timeout_s=120.0)


def _seed_campaign(
    session: Session,
    tmp_workspace: WorkspaceLayout,
    binaries: Binaries,
    *,
    recording_count: int = 1,
) -> tuple[Campaign, list[MediaAsset]]:
    campaign = Campaign(
        name="Alpha queue test",
        overlay_config='{"schema_version":1}',
        overlay_schema_version=1,
    )
    session.add(campaign)
    session.flush()

    talking_head_path = tmp_workspace.root / "head.mp4"
    _make_video(binaries, talking_head_path, duration=1)
    session.add(
        MediaAsset(
            campaign_id=campaign.id,
            role=AssetRole.TALKING_HEAD.value,
            source_path=str(talking_head_path),
            source_filename="head.mp4",
            probe_status=ProbeStatus.OK.value,
            duration_ms=1000,
            width=1280,
            height=720,
            fps=30.0,
            video_codec="h264",
            has_audio=1,
            trim_start_ms=0,
            trim_end_ms=1000,
            focal_x=0.5,
            focal_y=0.5,
        )
    )

    recordings: list[MediaAsset] = []
    for index in range(recording_count):
        recording_path = tmp_workspace.root / f"recording-{index}.mp4"
        _make_video(binaries, recording_path, duration=2)
        recording = MediaAsset(
            campaign_id=campaign.id,
            role=AssetRole.SCREEN_RECORDING.value,
            source_path=str(recording_path),
            source_filename=f"recording-{index}.mp4",
            company_name=f"Co {index + 1}",
            output_basename=f"Co {index + 1}",
            probe_status=ProbeStatus.OK.value,
            duration_ms=2000,
            width=1280,
            height=720,
            fps=30.0,
            video_codec="h264",
            has_audio=1,
            sort_order=index,
        )
        session.add(recording)
        recordings.append(recording)

    session.commit()
    session.refresh(campaign)
    for recording in recordings:
        session.refresh(recording)
    return campaign, recordings


def _drain_queue(
    session_factory: Callable[[], Session],
    binaries: Binaries,
    workspace: WorkspaceLayout,
) -> None:
    bus = EventBus(boot_id="test-boot")
    run_job = render_worker.build_run_job(binaries=binaries, workspace=workspace, event_bus=bus)
    for _ in range(50):
        claim_session = session_factory()
        try:
            job_id = render_worker.claim_next_job(claim_session)
        finally:
            claim_session.close()
        if job_id is None:
            return
        run_session = session_factory()
        try:
            run_job(run_session, job_id)
        finally:
            run_session.close()
    raise AssertionError("queue did not drain within the iteration bound")


# --- cold cache enqueue ------------------------------------------------------


def test_cold_cache_enqueues_alpha_prepare_pinned_above_video_jobs(
    session: Session, tmp_workspace: WorkspaceLayout, binaries: Binaries
) -> None:
    campaign, _ = _seed_campaign(session, tmp_workspace, binaries, recording_count=2)

    response = generate_videos(session, tmp_workspace, campaign.id)

    assert response.alpha_cache_warm is False
    assert response.enqueued_job_count == 3  # alpha + 2 videos
    job_types = [job.job_type for job in response.jobs]
    assert job_types[0] == JobType.ALPHA_PREPARE.value
    assert job_types[1:] == [JobType.VIDEO_RENDER.value, JobType.VIDEO_RENDER.value]

    alpha_job = response.jobs[0]
    for video_job in response.jobs[1:]:
        assert video_job.queue_position > alpha_job.queue_position
        assert video_job.depends_on_job_id == alpha_job.id


# --- warm cache enqueue ------------------------------------------------------


def test_warm_cache_skips_alpha_prepare_and_starts_encoding_directly(
    session: Session, tmp_workspace: WorkspaceLayout, binaries: Binaries
) -> None:
    campaign, recordings = _seed_campaign(session, tmp_workspace, binaries, recording_count=1)
    database = Database(tmp_workspace.database)

    # Cold run: builds and persists the alpha cache.
    first = generate_videos(session, tmp_workspace, campaign.id)
    assert first.alpha_cache_warm is False
    _drain_queue(database.session_factory, binaries, tmp_workspace)

    session.expire_all()
    session.refresh(campaign)
    assert campaign.alpha_cache_key is not None
    assert campaign.alpha_cache_path is not None

    # Mark the recording as unrendered so Generate has work again.
    recording = recordings[0]
    session.refresh(recording)
    recording.last_rendered_at = None
    recording.last_rendered_cache_key = None
    session.commit()

    warm = generate_videos(session, tmp_workspace, campaign.id)

    assert warm.alpha_cache_warm is True
    assert warm.enqueued_job_count == 1
    assert all(job.job_type == JobType.VIDEO_RENDER.value for job in warm.jobs)
    assert all(job.depends_on_job_id is None for job in warm.jobs)


# --- alpha failure cascade ---------------------------------------------------


def test_alpha_failure_cascades_to_dependents_with_the_same_root_cause(
    session: Session, tmp_workspace: WorkspaceLayout, binaries: Binaries
) -> None:
    campaign, _ = _seed_campaign(session, tmp_workspace, binaries, recording_count=2)
    database = Database(tmp_workspace.database)

    response = generate_videos(session, tmp_workspace, campaign.id)
    alpha_job_id = next(
        job.id for job in response.jobs if job.job_type == JobType.ALPHA_PREPARE.value
    )

    root_cause = "Simulated alpha build failure"
    bus = EventBus(boot_id="test-boot")
    run_job = render_worker.build_run_job(binaries=binaries, workspace=tmp_workspace, event_bus=bus)

    with patch(
        "outreachos_backend.modules.video_composer.render_worker.build_alpha_clip",
        side_effect=RenderError(root_cause),
    ):
        claim_session = database.session_factory()
        try:
            claimed = render_worker.claim_next_job(claim_session)
        finally:
            claim_session.close()
        assert claimed == alpha_job_id

        run_session = database.session_factory()
        try:
            run_job(run_session, alpha_job_id)
        finally:
            run_session.close()

    check = database.session_factory()
    try:
        alpha = check.get(RenderJob, alpha_job_id)
        assert alpha is not None
        assert alpha.status == JobStatus.FAILED.value
        assert alpha.error_message == root_cause

        dependents = check.scalars(
            select(RenderJob).where(RenderJob.depends_on_job_id == alpha_job_id)
        ).all()
        assert len(dependents) == 2
        for dependent in dependents:
            assert dependent.status == JobStatus.FAILED.value
            assert dependent.error_details == root_cause
            assert "alpha clip failed" in (dependent.error_message or "").lower()
    finally:
        check.close()
        database.dispose()


# --- cache invalidation ------------------------------------------------------


def test_update_overlay_config_invalidates_alpha_cache(
    session: Session, tmp_workspace: WorkspaceLayout
) -> None:
    campaign = Campaign(
        name="Invalidation test",
        overlay_config='{"schema_version":1}',
        overlay_schema_version=1,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    clip_rel = "cache/alpha/deadbeef.mov"
    clip_path = tmp_workspace.root / clip_rel
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"cached-alpha")
    campaign.alpha_cache_key = "deadbeef"
    campaign.alpha_cache_path = clip_rel
    session.commit()

    update_overlay_config(session, tmp_workspace, campaign.id, OverlayConfig())

    session.refresh(campaign)
    assert campaign.alpha_cache_key is None
    assert campaign.alpha_cache_path is None
    assert not clip_path.is_file()


def test_update_talking_head_trim_invalidates_alpha_cache(
    session: Session, tmp_workspace: WorkspaceLayout
) -> None:
    campaign = Campaign(
        name="Trim invalidation",
        overlay_config='{"schema_version":1}',
        overlay_schema_version=1,
    )
    session.add(campaign)
    session.flush()
    session.add(
        MediaAsset(
            campaign_id=campaign.id,
            role=AssetRole.TALKING_HEAD.value,
            source_path="/tmp/head.mp4",
            source_filename="head.mp4",
            probe_status=ProbeStatus.OK.value,
            duration_ms=5000,
            width=1280,
            height=720,
            fps=30.0,
            video_codec="h264",
            has_audio=1,
            trim_start_ms=0,
            trim_end_ms=5000,
            focal_x=0.5,
            focal_y=0.5,
        )
    )
    clip_rel = "cache/alpha/cafebabe.mov"
    clip_path = tmp_workspace.root / clip_rel
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"cached-alpha")
    campaign.alpha_cache_key = "cafebabe"
    campaign.alpha_cache_path = clip_rel
    session.commit()

    update_talking_head_trim(
        session,
        tmp_workspace,
        campaign.id,
        trim_start_ms=100,
        trim_end_ms=2000,
        focal_x=0.4,
        focal_y=0.6,
    )

    session.refresh(campaign)
    assert campaign.alpha_cache_key is None
    assert campaign.alpha_cache_path is None
    assert not clip_path.is_file()


# --- multi-video benchmark ---------------------------------------------------


def test_alpha_cache_reduces_multi_video_batch_time(
    tmp_workspace: WorkspaceLayout, binaries: Binaries
) -> None:
    """Warm batches skip alpha rebuild; total wall time should drop measurably."""
    database = Database(tmp_workspace.database)
    outcome = migrate.run_migrations(database.engine, database.path)
    assert outcome.ok, outcome.detail
    migrate.heal_app_settings(database.engine)

    session = database.session_factory()
    try:
        campaign, recordings = _seed_campaign(session, tmp_workspace, binaries, recording_count=3)

        cold_start = time.perf_counter()
        cold = generate_videos(session, tmp_workspace, campaign.id)
        assert cold.alpha_cache_warm is False
        _drain_queue(database.session_factory, binaries, tmp_workspace)
        cold_elapsed = time.perf_counter() - cold_start

        session.expire_all()
        session.refresh(campaign)
        assert campaign.alpha_cache_key is not None

        for recording in recordings:
            session.refresh(recording)
            recording.last_rendered_at = None
            recording.last_rendered_cache_key = None
        session.commit()

        warm_start = time.perf_counter()
        warm = generate_videos(session, tmp_workspace, campaign.id)
        assert warm.alpha_cache_warm is True
        _drain_queue(database.session_factory, binaries, tmp_workspace)
        warm_elapsed = time.perf_counter() - warm_start

        # Alpha build dominates a cold batch; warm should finish noticeably faster.
        assert warm_elapsed < cold_elapsed * 0.85, (
            f"expected warm ({warm_elapsed:.2f}s) to beat cold ({cold_elapsed:.2f}s)"
        )
    finally:
        session.close()
        database.dispose()
