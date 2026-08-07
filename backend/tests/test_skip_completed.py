"""Ticket 17: skip-completed and Re-render All.

Skip-completed is tracked on the recording row (survives export clearing the
queue). Cache-key drift makes a previously rendered recording eligible again.
Re-render All ignores currentness entirely.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.enums import AssetRole, JobType, ProbeStatus
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.models import Campaign, MediaAsset, RenderJob
from outreachos_backend.modules.video_composer.service import (
    generate_videos,
    get_generate_plan,
    update_overlay_config,
    update_talking_head_trim,
)
from outreachos_backend.rendering.binaries import Binaries, resolve_binaries
from outreachos_backend.rendering.config import OverlayConfig
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
    recording_count: int = 2,
) -> tuple[Campaign, MediaAsset, list[MediaAsset]]:
    campaign = Campaign(
        name="Skip-completed test",
        overlay_config='{"schema_version":1}',
        overlay_schema_version=1,
    )
    session.add(campaign)
    session.flush()

    talking_head_path = tmp_workspace.root / "head.mp4"
    _make_video(binaries, talking_head_path, duration=1)
    talking_head = MediaAsset(
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
    session.add(talking_head)

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
    session.refresh(talking_head)
    for recording in recordings:
        session.refresh(recording)
    return campaign, talking_head, recordings


def _stamp_current(
    session: Session,
    campaign: Campaign,
    recordings: list[MediaAsset],
    *,
    cache_key: str = "current-key",
) -> None:
    """Pretend a successful render under ``cache_key`` without running ffmpeg."""
    campaign.alpha_cache_key = cache_key
    campaign.alpha_cache_path = f"cache/alpha/{cache_key}.mov"
    for recording in recordings:
        recording.last_rendered_at = "2026-01-01T00:00:00Z"
        recording.last_rendered_cache_key = cache_key
    session.commit()


def test_generate_plan_counts_render_vs_skip(
    session: Session,
    tmp_workspace: WorkspaceLayout,
    binaries: Binaries,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign, _head, recordings = _seed_campaign(session, tmp_workspace, binaries)
    monkeypatch.setattr(
        "outreachos_backend.modules.video_composer.service._current_alpha_key",
        lambda *_args, **_kwargs: "current-key",
    )
    recordings[0].last_rendered_at = "2026-01-01T00:00:00Z"
    recordings[0].last_rendered_cache_key = "current-key"
    session.commit()

    plan = get_generate_plan(session, tmp_workspace, campaign.id)

    assert plan.total_eligible == 2
    assert plan.render_count == 1
    assert plan.skip_count == 1
    assert plan.all_current is False


def test_generate_skips_current_recordings_and_reports_counts(
    session: Session,
    tmp_workspace: WorkspaceLayout,
    binaries: Binaries,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign, _head, recordings = _seed_campaign(session, tmp_workspace, binaries)
    monkeypatch.setattr(
        "outreachos_backend.modules.video_composer.service._current_alpha_key",
        lambda *_args, **_kwargs: "current-key",
    )
    recordings[0].last_rendered_at = "2026-01-01T00:00:00Z"
    recordings[0].last_rendered_cache_key = "current-key"
    session.commit()

    response = generate_videos(session, tmp_workspace, campaign.id)

    assert response.render_count == 1
    assert response.skip_count == 1
    assert response.all_current is False
    video_jobs = [job for job in response.jobs if job.job_type == JobType.VIDEO_RENDER.value]
    assert len(video_jobs) == 1
    assert video_jobs[0].asset_id == recordings[1].id


def test_generate_all_current_reports_clearly_without_enqueueing(
    session: Session,
    tmp_workspace: WorkspaceLayout,
    binaries: Binaries,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign, _head, recordings = _seed_campaign(session, tmp_workspace, binaries)
    monkeypatch.setattr(
        "outreachos_backend.modules.video_composer.service._current_alpha_key",
        lambda *_args, **_kwargs: "current-key",
    )
    _stamp_current(session, campaign, recordings)

    plan = get_generate_plan(session, tmp_workspace, campaign.id)
    assert plan.all_current is True
    assert plan.render_count == 0
    assert plan.skip_count == 2

    response = generate_videos(session, tmp_workspace, campaign.id)
    assert response.all_current is True
    assert response.enqueued_job_count == 0
    assert response.render_count == 0
    assert response.skip_count == 2
    assert response.jobs == []

    jobs = session.scalars(select(RenderJob).where(RenderJob.campaign_id == campaign.id)).all()
    assert jobs == []


def test_skip_completed_survives_cleared_queue_jobs(
    session: Session,
    tmp_workspace: WorkspaceLayout,
    binaries: Binaries,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Export deletes completed jobs; skip-completed must not depend on them."""
    campaign, _head, recordings = _seed_campaign(session, tmp_workspace, binaries)
    monkeypatch.setattr(
        "outreachos_backend.modules.video_composer.service._current_alpha_key",
        lambda *_args, **_kwargs: "current-key",
    )
    _stamp_current(session, campaign, recordings)

    # Simulate a prior batch whose jobs were cleared after export.
    session.execute(delete(RenderJob).where(RenderJob.campaign_id == campaign.id))
    session.commit()

    response = generate_videos(session, tmp_workspace, campaign.id)
    assert response.all_current is True
    assert response.enqueued_job_count == 0


def test_cache_key_drift_from_overlay_change_re_enqueues(
    session: Session,
    tmp_workspace: WorkspaceLayout,
    binaries: Binaries,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign, _head, recordings = _seed_campaign(session, tmp_workspace, binaries)
    monkeypatch.setattr(
        "outreachos_backend.modules.video_composer.service._current_alpha_key",
        lambda *_args, **_kwargs: "old-key",
    )
    _stamp_current(session, campaign, recordings, cache_key="old-key")

    # Overlay edit invalidates the campaign alpha cache; after the edit the
    # current key no longer matches each recording's stamp.
    update_overlay_config(session, tmp_workspace, campaign.id, OverlayConfig(opacity=0.5))

    monkeypatch.setattr(
        "outreachos_backend.modules.video_composer.service._current_alpha_key",
        lambda *_args, **_kwargs: "new-key",
    )

    plan = get_generate_plan(session, tmp_workspace, campaign.id)
    assert plan.render_count == 2
    assert plan.skip_count == 0
    assert plan.all_current is False

    response = generate_videos(session, tmp_workspace, campaign.id)
    assert response.render_count == 2
    assert response.skip_count == 0
    assert sum(1 for job in response.jobs if job.job_type == JobType.VIDEO_RENDER.value) == 2


def test_cache_key_drift_from_trim_change_re_enqueues(
    session: Session,
    tmp_workspace: WorkspaceLayout,
    binaries: Binaries,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign, talking_head, recordings = _seed_campaign(session, tmp_workspace, binaries)
    monkeypatch.setattr(
        "outreachos_backend.modules.video_composer.service._current_alpha_key",
        lambda *_args, **_kwargs: "old-key",
    )
    _stamp_current(session, campaign, recordings, cache_key="old-key")

    update_talking_head_trim(
        session,
        tmp_workspace,
        campaign.id,
        trim_start_ms=0,
        trim_end_ms=900,
        focal_x=0.5,
        focal_y=0.5,
    )
    session.refresh(talking_head)
    assert talking_head.trim_end_ms == 900

    monkeypatch.setattr(
        "outreachos_backend.modules.video_composer.service._current_alpha_key",
        lambda *_args, **_kwargs: "new-key-after-trim",
    )

    response = generate_videos(session, tmp_workspace, campaign.id)
    assert response.render_count == 2
    assert response.skip_count == 0


def test_force_re_render_all_enqueues_everything(
    session: Session,
    tmp_workspace: WorkspaceLayout,
    binaries: Binaries,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign, _head, recordings = _seed_campaign(session, tmp_workspace, binaries)
    monkeypatch.setattr(
        "outreachos_backend.modules.video_composer.service._current_alpha_key",
        lambda *_args, **_kwargs: "current-key",
    )
    _stamp_current(session, campaign, recordings)

    response = generate_videos(session, tmp_workspace, campaign.id, force=True)

    assert response.all_current is False
    assert response.render_count == 2
    assert response.skip_count == 0
    assert sum(1 for job in response.jobs if job.job_type == JobType.VIDEO_RENDER.value) == 2
