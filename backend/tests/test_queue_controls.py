"""Ticket 19: pause, resume, cancel, retry, reorder."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.enums import JobStatus, JobType
from outreachos_backend.core.errors import ApiError
from outreachos_backend.core.events import EventBus
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer import render_worker
from outreachos_backend.modules.video_composer.models import Campaign, RenderJob
from outreachos_backend.modules.video_composer.service import (
    cancel_queue,
    cancel_render_job,
    is_campaign_locked,
    pause_render_queue,
    reorder_render_queue,
    resume_render_queue,
    retry_failed_jobs,
    retry_render_job,
)
from outreachos_backend.rendering.queue.pool import WorkerPool
from tests.conftest import TEST_TOKEN


@pytest.fixture
def database(tmp_workspace: WorkspaceLayout) -> Generator[Database, None, None]:
    db = Database(tmp_workspace.database)
    outcome = migrate.run_migrations(db.engine, db.path)
    assert outcome.ok, outcome.detail
    migrate.heal_app_settings(db.engine)
    try:
        yield db
    finally:
        db.dispose()


@pytest.fixture
def session(database: Database) -> Generator[Session, None, None]:
    db_session = database.session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture
def campaign(session: Session) -> Campaign:
    row = Campaign(
        name="Queue controls",
        overlay_config='{"schema_version":1}',
        overlay_schema_version=1,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _add_job(
    session: Session,
    campaign_id: str,
    *,
    status: JobStatus = JobStatus.WAITING,
    position: int = 1,
    job_type: JobType = JobType.VIDEO_RENDER,
    output_filename: str | None = "Acme.mp4",
    depends_on_job_id: str | None = None,
) -> RenderJob:
    job = RenderJob(
        campaign_id=campaign_id,
        job_type=job_type.value,
        status=status.value,
        queue_position=position,
        output_filename=output_filename,
        depends_on_job_id=depends_on_job_id,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def test_pause_then_resume_toggles_pool_flag(session: Session) -> None:
    pool: WorkerPool[str, Session] = WorkerPool(
        session_factory=lambda: session,
        claim_next=lambda _s: None,
        run_job=lambda _s, _j: None,
        concurrency=1,
    )

    paused = pause_render_queue(session, worker_pool=pool)
    assert paused.paused is True
    assert pool.paused

    resumed = resume_render_queue(session, worker_pool=pool)
    assert resumed.paused is False
    assert not pool.paused


def test_cancel_waiting_job_removes_row(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    job = _add_job(session, campaign.id)
    event_bus = MagicMock(spec=EventBus)

    result = cancel_render_job(session, tmp_workspace, event_bus, job.id)

    assert job.id not in {row.id for row in result.jobs}
    assert session.get(RenderJob, job.id) is None
    event_bus.campaign_lock_changed.assert_called_once_with(campaign.id, locked=False)


def test_cancel_encoding_job_requests_process_kill(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    job = _add_job(session, campaign.id, status=JobStatus.ENCODING)
    event_bus = MagicMock(spec=EventBus)

    with patch("outreachos_backend.modules.video_composer.service.request_cancel") as mocked_cancel:
        cancel_render_job(session, tmp_workspace, event_bus, job.id)
        mocked_cancel.assert_called_once_with(job.id)

    assert session.get(RenderJob, job.id) is None


def test_cancel_queue_kills_in_flight_and_leaves_no_active_jobs(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    waiting = _add_job(session, campaign.id, status=JobStatus.WAITING, position=1)
    encoding = _add_job(session, campaign.id, status=JobStatus.ENCODING, position=2)
    failed = _add_job(session, campaign.id, status=JobStatus.FAILED, position=3)
    event_bus = MagicMock(spec=EventBus)

    with patch("outreachos_backend.modules.video_composer.service.request_cancel") as mocked_cancel:
        detail = cancel_queue(session, event_bus, tmp_workspace, campaign.id)
        mocked_cancel.assert_called_once_with(encoding.id)

    assert detail.is_locked is False
    remaining = session.scalars(select(RenderJob).where(RenderJob.campaign_id == campaign.id)).all()
    assert [job.id for job in remaining] == [failed.id]
    assert session.get(RenderJob, waiting.id) is None


def test_retry_failed_job_resets_cleanly(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    job = _add_job(session, campaign.id, status=JobStatus.FAILED)
    job.error_message = "boom"
    job.error_details = "stderr"
    job.progress_pct = 40.0
    job.finished_at = "2026-01-01T00:00:00Z"
    session.commit()
    event_bus = MagicMock(spec=EventBus)
    pool = MagicMock(spec=WorkerPool)
    pool.paused = False

    result = retry_render_job(session, tmp_workspace, event_bus, job.id, worker_pool=pool)

    refreshed = session.get(RenderJob, job.id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.WAITING.value
    assert refreshed.error_message is None
    assert refreshed.error_details is None
    assert refreshed.progress_pct == 0.0
    assert refreshed.finished_at is None
    assert any(row.id == job.id and row.status == "waiting" for row in result.jobs)
    pool.wake.assert_called_once()


def test_reorder_persists_new_positions(session: Session, campaign: Campaign) -> None:
    first = _add_job(session, campaign.id, position=1, output_filename="A.mp4")
    second = _add_job(session, campaign.id, position=2, output_filename="B.mp4")
    event_bus = MagicMock(spec=EventBus)

    result = reorder_render_queue(session, event_bus, [second.id, first.id])

    assert [job.id for job in result.jobs] == [second.id, first.id]
    session.refresh(first)
    session.refresh(second)
    assert second.queue_position < first.queue_position


def test_reorder_rejects_moving_encoding_job(session: Session, campaign: Campaign) -> None:
    waiting = _add_job(session, campaign.id, status=JobStatus.WAITING, position=1)
    encoding = _add_job(session, campaign.id, status=JobStatus.ENCODING, position=2)
    event_bus = MagicMock(spec=EventBus)

    with pytest.raises(ApiError) as exc_info:
        reorder_render_queue(session, event_bus, [encoding.id, waiting.id])

    assert exc_info.value.status_code == 422


def test_reorder_keeps_alpha_above_campaign_videos(session: Session, campaign: Campaign) -> None:
    alpha = _add_job(
        session,
        campaign.id,
        position=1,
        job_type=JobType.ALPHA_PREPARE,
        output_filename=None,
    )
    video = _add_job(session, campaign.id, position=2)
    event_bus = MagicMock(spec=EventBus)

    with pytest.raises(ApiError) as exc_info:
        reorder_render_queue(session, event_bus, [video.id, alpha.id])

    assert exc_info.value.status_code == 422


@pytest.fixture
def app_with_pool(app: FastAPI, tmp_workspace: WorkspaceLayout) -> FastAPI:
    database = Database(tmp_workspace.database)
    outcome = migrate.run_migrations(database.engine, database.path)
    assert outcome.ok, outcome.detail
    migrate.heal_app_settings(database.engine)
    migrate.apply_outcome(app.state.runtime.report, outcome)
    app.state.database = database

    pool: WorkerPool[str, Session] = WorkerPool(
        session_factory=database.session_factory,
        claim_next=lambda _s: None,
        run_job=lambda _s, _j: None,
        concurrency=1,
        poll_interval_s=30.0,
        name="test-queue-controls",
    )
    app.state.worker_pool = pool
    return app


@pytest.mark.asyncio
async def test_pause_route_sets_paused(app_with_pool: FastAPI) -> None:
    pool: WorkerPool[str, Session] = app_with_pool.state.worker_pool

    async with AsyncClient(
        transport=ASGITransport(app=app_with_pool),
        base_url="http://127.0.0.1/api/v1",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as client:
        body = (await client.post("/render-queue/pause")).json()

    assert body["paused"] is True
    assert pool.paused


def test_cancel_alpha_removes_waiting_dependents_and_unlocks(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    alpha = _add_job(
        session,
        campaign.id,
        position=1,
        job_type=JobType.ALPHA_PREPARE,
        output_filename=None,
    )
    video = _add_job(
        session,
        campaign.id,
        position=2,
        depends_on_job_id=alpha.id,
    )
    event_bus = MagicMock(spec=EventBus)

    assert is_campaign_locked(session, campaign.id)

    result = cancel_render_job(session, tmp_workspace, event_bus, alpha.id)

    assert session.get(RenderJob, alpha.id) is None
    assert session.get(RenderJob, video.id) is None
    assert video.id not in {row.id for row in result.jobs}
    assert not is_campaign_locked(session, campaign.id)
    event_bus.campaign_lock_changed.assert_called_once_with(campaign.id, locked=False)


def test_claim_admits_job_with_dangling_dependency(session: Session, campaign: Campaign) -> None:
    video = _add_job(
        session,
        campaign.id,
        position=1,
        depends_on_job_id="missing-alpha-id",
    )

    claimed_id = render_worker.claim_next_job(session)

    assert claimed_id == video.id
    session.refresh(video)
    assert video.status == JobStatus.PREPARING.value


def test_cancel_waiting_job_leaves_existing_final_output(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    out_dir = tmp_workspace.outputs / campaign.id
    out_dir.mkdir(parents=True)
    final = out_dir / "Acme.mp4"
    final.write_bytes(b"previous-good-render")
    job = _add_job(session, campaign.id, status=JobStatus.WAITING)
    event_bus = MagicMock(spec=EventBus)

    cancel_render_job(session, tmp_workspace, event_bus, job.id)

    assert final.is_file()
    assert final.read_bytes() == b"previous-good-render"


def test_retry_failed_leaves_previous_good_output(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    out_dir = tmp_workspace.outputs / campaign.id
    out_dir.mkdir(parents=True)
    final = out_dir / "Acme.mp4"
    final.write_bytes(b"previous-good-render")
    job = _add_job(session, campaign.id, status=JobStatus.FAILED)
    job.error_message = "boom"
    session.commit()
    event_bus = MagicMock(spec=EventBus)

    retry_failed_jobs(session, tmp_workspace, event_bus)

    assert final.is_file()
    assert final.read_bytes() == b"previous-good-render"
    session.refresh(job)
    assert job.status == JobStatus.WAITING.value


def test_retry_single_failed_video_resets_failed_alpha_dependency(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    alpha = _add_job(
        session,
        campaign.id,
        status=JobStatus.FAILED,
        position=1,
        job_type=JobType.ALPHA_PREPARE,
        output_filename=None,
    )
    alpha.error_message = "alpha boom"
    session.commit()
    video = _add_job(
        session,
        campaign.id,
        status=JobStatus.FAILED,
        position=2,
        depends_on_job_id=alpha.id,
    )
    video.error_message = "cascaded"
    session.commit()
    event_bus = MagicMock(spec=EventBus)

    retry_render_job(session, tmp_workspace, event_bus, video.id)

    session.refresh(alpha)
    session.refresh(video)
    assert alpha.status == JobStatus.WAITING.value
    assert alpha.error_message is None
    assert video.status == JobStatus.WAITING.value
    assert video.error_message is None
