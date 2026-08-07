"""Ticket 15: job claiming, the six-state machine, and a real end-to-end render.

``test_claim_*`` cover the queue logic without ffmpeg. ``test_generate_videos_*``
drive the real render engine through a full campaign, so they use the same
``ffmpeg_dir``-skipping fixture pattern as ``test_campaigns_route.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.enums import AssetRole, JobStatus, JobType, ProbeStatus
from outreachos_backend.core.events import EventBus
from outreachos_backend.core.models import AppSettings
from outreachos_backend.core.settings_service import resolve_quality
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer import render_worker
from outreachos_backend.modules.video_composer.models import Campaign, MediaAsset, RenderJob
from outreachos_backend.modules.video_composer.service import (
    generate_videos,
    reset_interrupted_jobs,
)
from outreachos_backend.rendering.binaries import Binaries, resolve_binaries
from outreachos_backend.rendering.process import run_tool

REPO_ROOT = Path(__file__).resolve().parents[2]
FFMPEG_DIR = REPO_ROOT / "vendor" / "ffmpeg"


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


@pytest.fixture
def campaign(session: Session) -> Campaign:
    campaign = Campaign(
        name="Test campaign",
        overlay_config='{"schema_version":1}',
        overlay_schema_version=1,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def _make_job(
    session: Session,
    campaign: Campaign,
    *,
    job_type: str,
    position: int,
    depends_on_job_id: str | None = None,
    status: str = JobStatus.WAITING.value,
    output_filename: str | None = None,
    output_path: str | None = None,
) -> RenderJob:
    job = RenderJob(
        campaign_id=campaign.id,
        job_type=job_type,
        status=status,
        queue_position=position,
        depends_on_job_id=depends_on_job_id,
        output_filename=output_filename,
        output_path=output_path,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


# --- claim_next_job ----------------------------------------------------------


def test_claim_returns_none_on_an_empty_queue(session: Session) -> None:
    assert render_worker.claim_next_job(session) is None


def test_claim_picks_the_lowest_queue_position(session: Session, campaign: Campaign) -> None:
    second = _make_job(session, campaign, job_type=JobType.VIDEO_RENDER.value, position=2)
    first = _make_job(session, campaign, job_type=JobType.VIDEO_RENDER.value, position=1)

    claimed_id = render_worker.claim_next_job(session)

    assert claimed_id == first.id
    session.refresh(first)
    session.refresh(second)
    assert first.status == JobStatus.PREPARING.value
    assert first.attempts == 1
    assert first.started_at is not None
    assert second.status == JobStatus.WAITING.value


def test_claim_skips_a_job_waiting_on_an_unfinished_dependency(
    session: Session, campaign: Campaign
) -> None:
    alpha = _make_job(session, campaign, job_type=JobType.ALPHA_PREPARE.value, position=1)
    video = _make_job(
        session,
        campaign,
        job_type=JobType.VIDEO_RENDER.value,
        position=2,
        depends_on_job_id=alpha.id,
    )

    claimed_id = render_worker.claim_next_job(session)

    assert claimed_id == alpha.id
    session.refresh(video)
    assert video.status == JobStatus.WAITING.value


def test_claim_admits_a_job_once_its_dependency_completed(
    session: Session, campaign: Campaign
) -> None:
    alpha = _make_job(
        session,
        campaign,
        job_type=JobType.ALPHA_PREPARE.value,
        position=1,
        status=JobStatus.COMPLETED.value,
    )
    video = _make_job(
        session,
        campaign,
        job_type=JobType.VIDEO_RENDER.value,
        position=2,
        depends_on_job_id=alpha.id,
    )

    claimed_id = render_worker.claim_next_job(session)

    assert claimed_id == video.id


def test_claim_does_not_reclaim_an_already_claimed_job(
    session: Session, campaign: Campaign
) -> None:
    job = _make_job(session, campaign, job_type=JobType.VIDEO_RENDER.value, position=1)

    first_claim = render_worker.claim_next_job(session)
    second_claim = render_worker.claim_next_job(session)

    assert first_claim == job.id
    assert second_claim is None


# --- reset_interrupted_jobs ----------------------------------------------------


def test_reset_interrupted_jobs_resets_mid_flight_statuses_to_waiting(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    rendering = _make_job(
        session,
        campaign,
        job_type=JobType.ALPHA_PREPARE.value,
        position=1,
        status=JobStatus.RENDERING.value,
    )
    encoding = _make_job(
        session,
        campaign,
        job_type=JobType.VIDEO_RENDER.value,
        position=2,
        status=JobStatus.ENCODING.value,
    )
    waiting = _make_job(session, campaign, job_type=JobType.VIDEO_RENDER.value, position=3)
    completed = _make_job(
        session,
        campaign,
        job_type=JobType.VIDEO_RENDER.value,
        position=4,
        status=JobStatus.COMPLETED.value,
    )

    reset_count = reset_interrupted_jobs(session, tmp_workspace)

    assert reset_count == 2
    session.refresh(rendering)
    session.refresh(encoding)
    session.refresh(waiting)
    session.refresh(completed)
    assert rendering.status == JobStatus.WAITING.value
    assert encoding.status == JobStatus.WAITING.value
    assert waiting.status == JobStatus.WAITING.value
    assert completed.status == JobStatus.COMPLETED.value


def test_reset_interrupted_jobs_deletes_part_files_and_leaves_completed_outputs(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    """Ticket 22: crash mid-encode leaves ``*.part.mp4``; recovery must scrub it.

    Completed outputs from earlier jobs stay. A final-looking file at the
    target basename (crash between rename and commit, or a prior good render)
    is also left intact — the next encode overwrites it atomically.
    """
    out_dir = tmp_workspace.outputs / campaign.id
    out_dir.mkdir(parents=True)

    completed_file = out_dir / "Acme.mp4"
    completed_file.write_bytes(b"complete-output")
    completed = _make_job(
        session,
        campaign,
        job_type=JobType.VIDEO_RENDER.value,
        position=1,
        status=JobStatus.COMPLETED.value,
        output_filename="Acme.mp4",
        output_path=completed_file.relative_to(tmp_workspace.root).as_posix(),
    )

    part_file = out_dir / "Beta.mp4.1234-deadbeef.part.mp4"
    part_file.write_bytes(b"truncated-partial")
    # Crash between rename and DB commit can leave a final-looking file; keep it.
    orphan_final = out_dir / "Beta.mp4"
    orphan_final.write_bytes(b"not-committed")
    encoding = _make_job(
        session,
        campaign,
        job_type=JobType.VIDEO_RENDER.value,
        position=2,
        status=JobStatus.ENCODING.value,
        output_filename="Beta.mp4",
    )

    reset_count = reset_interrupted_jobs(session, tmp_workspace)

    assert reset_count == 1
    session.refresh(encoding)
    session.refresh(completed)
    assert encoding.status == JobStatus.WAITING.value
    assert encoding.progress_pct == 0.0
    assert encoding.started_at is None
    assert completed.status == JobStatus.COMPLETED.value
    assert completed_file.is_file()
    assert completed_file.read_bytes() == b"complete-output"
    assert not part_file.exists()
    assert orphan_final.is_file()
    assert orphan_final.read_bytes() == b"not-committed"


# --- generate_videos + a real end-to-end render -------------------------------


@pytest.fixture(scope="session")
def ffmpeg_dir() -> Path:
    if not (FFMPEG_DIR / "ffmpeg.exe").is_file():
        pytest.skip("vendor/ffmpeg not present — run scripts/fetch-ffmpeg.ps1")
    return FFMPEG_DIR


@pytest.fixture(scope="session")
def binaries(ffmpeg_dir: Path) -> Binaries:
    return resolve_binaries(ffmpeg_dir)


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


def _drain_queue(
    session_factory: Callable[[], Session],
    binaries: Binaries,
    workspace: WorkspaceLayout,
) -> None:
    """Synchronously run the pool's claim/run pair to completion, no threads."""
    bus = EventBus(boot_id="test-boot")
    run_job = render_worker.build_run_job(binaries=binaries, workspace=workspace, event_bus=bus)
    for _ in range(20):  # generous bound; a stuck queue should fail loudly, not hang
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


def test_generate_videos_renders_a_single_recording_end_to_end(
    tmp_workspace: WorkspaceLayout, binaries: Binaries
) -> None:
    database = Database(tmp_workspace.database)
    outcome = migrate.run_migrations(database.engine, database.path)
    assert outcome.ok, outcome.detail
    migrate.heal_app_settings(database.engine)

    session = database.session_factory()
    try:
        campaign = Campaign(
            name="Acme",
            overlay_config='{"schema_version":1}',
            overlay_schema_version=1,
        )
        session.add(campaign)
        session.flush()

        talking_head_path = tmp_workspace.root / "head.mp4"
        _make_video(binaries, talking_head_path, duration=1)
        recording_path = tmp_workspace.root / "recording.mp4"
        _make_video(binaries, recording_path, duration=2)

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
        session.add(
            MediaAsset(
                campaign_id=campaign.id,
                role=AssetRole.SCREEN_RECORDING.value,
                source_path=str(recording_path),
                source_filename="recording.mp4",
                company_name="Acme Co",
                output_basename="Acme Co",
                probe_status=ProbeStatus.OK.value,
                duration_ms=2000,
                width=1280,
                height=720,
                fps=30.0,
                video_codec="h264",
                has_audio=1,
                sort_order=0,
            )
        )
        session.commit()

        response = generate_videos(session, tmp_workspace, campaign.id)
        assert response.alpha_cache_warm is False
        assert response.enqueued_job_count == 2  # alpha_prepare + one video_render
        assert {job.job_type for job in response.jobs} == {"alpha_prepare", "video_render"}

        _drain_queue(database.session_factory, binaries, tmp_workspace)

        session.expire_all()
        all_jobs = session.scalars(
            select(RenderJob).where(RenderJob.campaign_id == campaign.id)
        ).all()
        assert len(all_jobs) == 2
        for job in all_jobs:
            assert job.status == JobStatus.COMPLETED.value, job.error_details
            assert job.progress_pct == 100.0

        video_job = next(job for job in all_jobs if job.job_type == "video_render")
        assert video_job.output_path == f"outputs/{campaign.id}/Acme Co.mp4"
        output_file = tmp_workspace.root / video_job.output_path
        assert output_file.is_file()
        assert output_file.stat().st_size > 0

        session.refresh(campaign)
        assert campaign.alpha_cache_key is not None

        recording = session.scalars(
            select(MediaAsset).where(
                MediaAsset.campaign_id == campaign.id,
                MediaAsset.role == AssetRole.SCREEN_RECORDING.value,
            )
        ).one()
        assert recording.last_rendered_at is not None
        assert recording.last_rendered_cache_key == campaign.alpha_cache_key

        # Ticket 17: a second Generate call reports all-current and enqueues nothing.
        second = generate_videos(session, tmp_workspace, campaign.id)
        assert second.all_current is True
        assert second.enqueued_job_count == 0
        assert second.render_count == 0
        assert second.skip_count == 1
    finally:
        session.close()
        database.dispose()


def test_generate_videos_inherits_global_quality_preset(session: Session) -> None:
    settings = session.query(AppSettings).filter(AppSettings.id == 1).one()
    settings.quality_preset = "draft"
    session.commit()

    campaign = Campaign(
        name="Quality inherit",
        overlay_config='{"schema_version":1}',
        overlay_schema_version=1,
        quality_override=None,
    )
    session.add(campaign)
    session.commit()

    assert resolve_quality(session, quality_override=campaign.quality_override) == "draft"
