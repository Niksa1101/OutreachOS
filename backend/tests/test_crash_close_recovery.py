"""Ticket 22: crash/close recovery — pause-on-boot surface and Resume API."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.enums import JobStatus, JobType
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.models import Campaign, RenderJob
from outreachos_backend.modules.video_composer.service import reset_interrupted_jobs
from outreachos_backend.rendering.queue.pool import WorkerPool
from tests.conftest import TEST_TOKEN


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
def app_with_paused_pool(app: FastAPI, tmp_workspace: WorkspaceLayout) -> FastAPI:
    database = Database(tmp_workspace.database)
    outcome = migrate.run_migrations(database.engine, database.path)
    assert outcome.ok, outcome.detail
    migrate.heal_app_settings(database.engine)
    migrate.apply_outcome(app.state.runtime.report, outcome)
    app.state.database = database

    with database.session_factory() as session:
        campaign = Campaign(
            name="Recovery campaign",
            overlay_config='{"schema_version":1}',
            overlay_schema_version=1,
        )
        session.add(campaign)
        session.flush()

        out_dir = tmp_workspace.outputs / campaign.id
        out_dir.mkdir(parents=True)
        part = out_dir / "Acme.mp4.99-abcdef01.part.mp4"
        part.write_bytes(b"truncated")

        session.add(
            RenderJob(
                campaign_id=campaign.id,
                job_type=JobType.VIDEO_RENDER.value,
                status=JobStatus.ENCODING.value,
                queue_position=1,
                output_filename="Acme.mp4",
                progress_pct=42.0,
            )
        )
        session.add(
            RenderJob(
                campaign_id=campaign.id,
                job_type=JobType.VIDEO_RENDER.value,
                status=JobStatus.COMPLETED.value,
                queue_position=2,
                output_filename="Done.mp4",
                output_path=(tmp_workspace.outputs / campaign.id / "Done.mp4")
                .relative_to(tmp_workspace.root)
                .as_posix(),
                progress_pct=100.0,
            )
        )
        (out_dir / "Done.mp4").write_bytes(b"kept")
        session.commit()

        reset_count = reset_interrupted_jobs(session, tmp_workspace)
        assert reset_count == 1
        assert not part.exists()
        assert (out_dir / "Done.mp4").is_file()

    def _claim(_session: Session) -> str | None:
        return None

    def _run(_session: Session, _job_id: str) -> None:
        return None

    pool: WorkerPool[str, Session] = WorkerPool(
        session_factory=database.session_factory,
        claim_next=_claim,
        run_job=_run,
        concurrency=1,
        poll_interval_s=30.0,
        name="test-recovery",
    )
    pool.pause(show_resume_prompt=True)
    app.state.worker_pool = pool
    return app


async def test_render_queue_reports_recovery_pause(app_with_paused_pool: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_paused_pool),
        base_url="http://127.0.0.1/api/v1",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as client:
        body = (await client.get("/render-queue")).json()

    assert body["paused"] is True
    assert body["show_resume_prompt"] is True
    statuses = {job["output_filename"]: job["status"] for job in body["jobs"]}
    assert statuses["Acme.mp4"] == "waiting"
    assert statuses["Done.mp4"] == "completed"
    acme = next(job for job in body["jobs"] if job["output_filename"] == "Acme.mp4")
    assert acme["progress_pct"] == 0.0


async def test_resume_clears_recovery_prompt(app_with_paused_pool: FastAPI) -> None:
    pool: WorkerPool[str, Session] = app_with_paused_pool.state.worker_pool

    async with AsyncClient(
        transport=ASGITransport(app=app_with_paused_pool),
        base_url="http://127.0.0.1/api/v1",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as client:
        body = (await client.post("/render-queue/resume")).json()

    assert body["paused"] is False
    assert body["show_resume_prompt"] is False
    assert not pool.paused
    assert not pool.show_resume_prompt


def test_reset_interrupted_deletes_partials_but_keeps_prior_final(
    session: Session, tmp_workspace: WorkspaceLayout
) -> None:
    campaign = Campaign(
        name="Keep finals",
        overlay_config='{"schema_version":1}',
        overlay_schema_version=1,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    out_dir = tmp_workspace.outputs / campaign.id
    out_dir.mkdir(parents=True)
    final = out_dir / "Acme.mp4"
    final.write_bytes(b"previous-good-render")
    part = out_dir / "Acme.mp4.42-deadbeef.part.mp4"
    part.write_bytes(b"truncated")

    session.add(
        RenderJob(
            campaign_id=campaign.id,
            job_type=JobType.VIDEO_RENDER.value,
            status=JobStatus.ENCODING.value,
            queue_position=1,
            output_filename="Acme.mp4",
            progress_pct=55.0,
        )
    )
    session.commit()

    assert reset_interrupted_jobs(session, tmp_workspace) == 1
    assert not part.exists()
    assert final.is_file()
    assert final.read_bytes() == b"previous-good-render"
