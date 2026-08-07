"""Ticket 20: mid-batch failure continues, stores capped detail, retry works."""

from __future__ import annotations

import logging
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
from outreachos_backend.modules.video_composer.service import generate_videos, retry_failed_jobs
from outreachos_backend.rendering.binaries import Binaries, resolve_binaries
from outreachos_backend.rendering.config import ScreenRecordingJob
from outreachos_backend.rendering.errors import cap_stderr, format_command
from outreachos_backend.rendering.process import run_tool
from outreachos_backend.rendering.render import JobResult
from outreachos_backend.rendering.render import render_one as real_render_one

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


def _make_video(binaries: Binaries, path: Path, *, duration: int = 1) -> None:
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
    recording_count: int,
) -> Campaign:
    campaign = Campaign(
        name="Failure surfacing",
        overlay_config='{"schema_version":1}',
        overlay_schema_version=1,
    )
    session.add(campaign)
    session.flush()

    head = tmp_workspace.root / "head.mp4"
    _make_video(binaries, head, duration=1)
    session.add(
        MediaAsset(
            campaign_id=campaign.id,
            role=AssetRole.TALKING_HEAD.value,
            source_path=str(head),
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

    for index in range(recording_count):
        path = tmp_workspace.root / f"rec-{index}.mp4"
        _make_video(binaries, path, duration=2)
        session.add(
            MediaAsset(
                campaign_id=campaign.id,
                role=AssetRole.SCREEN_RECORDING.value,
                source_path=str(path),
                source_filename=path.name,
                company_name=f"Company {index + 1}",
                output_basename=f"Company {index + 1}",
                probe_status=ProbeStatus.OK.value,
                duration_ms=2000,
                width=1280,
                height=720,
                fps=30.0,
                video_codec="h264",
                has_audio=1,
                sort_order=index,
            )
        )

    session.commit()
    session.refresh(campaign)
    return campaign


def _drain_queue(
    session_factory: Callable[[], Session],
    binaries: Binaries,
    workspace: WorkspaceLayout,
    *,
    max_iterations: int = 20,
) -> None:
    bus = EventBus(boot_id="failure-surfacing")
    run_job = render_worker.build_run_job(binaries=binaries, workspace=workspace, event_bus=bus)
    for _ in range(max_iterations):
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


def test_cap_stderr_keeps_head_and_tail() -> None:
    huge = "A" * 40_000 + "MIDDLE" + "B" * 40_000
    capped = cap_stderr(huge)
    assert len(capped) <= 64 * 1024
    assert capped.startswith("A" * 100)
    assert capped.endswith("B" * 100)
    assert "bytes elided" in capped
    assert "MIDDLE" not in capped


def test_format_command_is_pasteable_on_this_platform() -> None:
    command = [r"C:\Program Files\ffmpeg\ffmpeg.exe", "-i", "in file.mp4", "out.mp4"]
    formatted = format_command(command)
    assert "ffmpeg" in formatted
    assert "out.mp4" in formatted


def test_mid_batch_failure_continues_stores_detail_and_retries(
    session: Session,
    tmp_workspace: WorkspaceLayout,
    binaries: Binaries,
    caplog: pytest.LogCaptureFixture,
) -> None:
    campaign = _seed_campaign(session, tmp_workspace, binaries, recording_count=3)
    database = Database(tmp_workspace.database)

    response = generate_videos(session, tmp_workspace, campaign.id)
    video_ids = [job.id for job in response.jobs if job.job_type == JobType.VIDEO_RENDER.value]
    assert len(video_ids) == 3
    fail_id = video_ids[1]

    huge_stderr = "HEAD-" + ("x" * 70_000) + "-TAIL-ERROR-LINE"
    fail_command = [str(binaries.ffmpeg), "-y", "-i", "broken.mp4", "out.mp4"]
    injected = {"failed": False}

    def flaky_render_one(*args: object, **kwargs: object) -> JobResult:
        job = args[3]
        assert isinstance(job, ScreenRecordingJob)
        if job.output_basename == "Company 2" and not injected["failed"]:
            injected["failed"] = True
            return JobResult(
                None,
                False,
                error=f"FFmpeg exited 1\n{huge_stderr}",
                command=fail_command,
            )
        return real_render_one(*args, **kwargs)  # type: ignore[arg-type]

    with (
        patch(
            "outreachos_backend.modules.video_composer.render_worker.render_one",
            side_effect=flaky_render_one,
        ),
        caplog.at_level(
            logging.ERROR,
            logger="outreachos_backend.modules.video_composer.render_worker",
        ),
    ):
        _drain_queue(database.session_factory, binaries, tmp_workspace)

    session.expire_all()
    jobs = session.scalars(select(RenderJob).where(RenderJob.campaign_id == campaign.id)).all()
    by_status: dict[str, list[RenderJob]] = {}
    for job in jobs:
        by_status.setdefault(job.status, []).append(job)

    assert len(by_status.get(JobStatus.COMPLETED.value, [])) == 3  # alpha + 2 videos
    assert len(by_status.get(JobStatus.FAILED.value, [])) == 1

    failed = session.get(RenderJob, fail_id)
    assert failed is not None
    assert failed.status == JobStatus.FAILED.value
    assert failed.error_message == "FFmpeg failed while encoding this video."
    assert failed.error_details is not None
    assert len(failed.error_details) <= 64 * 1024
    assert "bytes elided" in failed.error_details
    assert failed.error_details.startswith("FFmpeg exited 1")
    assert "TAIL-ERROR-LINE" in failed.error_details
    assert failed.ffmpeg_command == format_command(fail_command)

    # Full (uncapped) stderr reached the rolling log before the DB cap.
    assert any(
        "HEAD-" in record.message and "TAIL-ERROR-LINE" in record.message
        for record in caplog.records
    )

    # Later jobs still finished — the injected failure did not stop the batch.
    later = session.get(RenderJob, video_ids[2])
    assert later is not None
    assert later.status == JobStatus.COMPLETED.value

    bus = EventBus(boot_id="retry")
    retry = retry_failed_jobs(session, tmp_workspace, bus)
    assert retry.retried_job_count == 1
    assert retry.jobs[0].id == fail_id
    assert retry.jobs[0].status == JobStatus.WAITING.value

    session.expire_all()
    refreshed = session.get(RenderJob, fail_id)
    assert refreshed is not None
    assert refreshed.error_message is None
    assert refreshed.error_details is None
    assert refreshed.ffmpeg_command is None

    # Unpatched path for the retry: remove the failure injection.
    _drain_queue(database.session_factory, binaries, tmp_workspace)

    session.expire_all()
    final = session.scalars(select(RenderJob).where(RenderJob.campaign_id == campaign.id)).all()
    assert all(job.status == JobStatus.COMPLETED.value for job in final), [
        (job.output_filename, job.status, job.error_message) for job in final
    ]

    database.dispose()
