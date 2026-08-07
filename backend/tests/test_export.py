"""Ticket 23: outputs staging view and Export All."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.enums import AssetRole, JobStatus, JobType, ProbeStatus
from outreachos_backend.core.models import AppSettings
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.models import Campaign, MediaAsset, RenderJob
from tests.conftest import TEST_TOKEN

REPO_ROOT = Path(__file__).resolve().parents[2]
FFMPEG_DIR = REPO_ROOT / "vendor" / "ffmpeg"


@pytest.fixture(scope="session")
def ffmpeg_dir() -> Path:
    if not (FFMPEG_DIR / "ffmpeg.exe").is_file():
        pytest.skip("vendor/ffmpeg not present — run scripts/fetch-ffmpeg.ps1")
    return FFMPEG_DIR


@pytest.fixture
def app_with_database(app: FastAPI, tmp_workspace: WorkspaceLayout, ffmpeg_dir: Path) -> FastAPI:
    database = Database(tmp_workspace.database)
    outcome = migrate.run_migrations(database.engine, database.path)
    assert outcome.ok, outcome.detail
    migrate.heal_app_settings(database.engine)

    migrate.apply_outcome(app.state.runtime.report, outcome)
    app.state.database = database
    app.state.runtime.ffmpeg_dir = ffmpeg_dir
    return app


async def client_for(app: FastAPI) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1/api/v1",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )


def _seed_staged_recording(
    session: Session,
    tmp_workspace: WorkspaceLayout,
    campaign_id: str,
    *,
    company_name: str,
    sort_order: int = 0,
    output_bytes: bytes = b"staged-output",
    status: str = JobStatus.COMPLETED.value,
    source_path: str | None = None,
) -> tuple[MediaAsset, RenderJob, Path]:
    output_dir = tmp_workspace.outputs / campaign_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{company_name}.mp4"
    output_file.write_bytes(output_bytes)

    resolved_source = source_path or f"C:/videos/{company_name.replace(' ', '-').lower()}.mp4"

    asset = MediaAsset(
        campaign_id=campaign_id,
        role=AssetRole.SCREEN_RECORDING.value,
        source_path=resolved_source,
        source_filename=f"{company_name}.mp4",
        company_name=company_name,
        output_basename=company_name,
        sort_order=sort_order,
        probe_status=ProbeStatus.OK.value,
        duration_ms=2000,
        width=640,
        height=480,
        fps=30.0,
        video_codec="h264",
        has_audio=0,
        last_rendered_at="2026-01-01T00:00:00Z",
    )
    session.add(asset)
    session.flush()

    job = RenderJob(
        campaign_id=campaign_id,
        asset_id=asset.id,
        job_type=JobType.VIDEO_RENDER.value,
        status=status,
        queue_position=sort_order + 1,
        output_path=output_file.relative_to(tmp_workspace.root).as_posix(),
        output_filename=output_file.name,
        finished_at="2026-01-01T00:00:00Z" if status == JobStatus.COMPLETED.value else None,
    )
    session.add(job)
    session.commit()
    session.refresh(asset)
    session.refresh(job)
    return asset, job, output_file


async def test_outputs_empty_for_new_campaign(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Fresh"})).json()
        body = (await client.get(f"/campaigns/{created['id']}/outputs")).json()

    assert body["outputs"] == []
    assert body["exportable_count"] == 0
    assert body["total_size_bytes"] == 0
    assert body["default_export_path"] is None


async def test_outputs_lists_staged_files_excluding_partials(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Staged"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        _seed_staged_recording(session, tmp_workspace, campaign_id, company_name="Acme Corp")

    output_dir = tmp_workspace.outputs / campaign_id
    (output_dir / "Beta Inc.mp4.12345-abcd.part.mp4").write_bytes(b"partial")

    async with await client_for(app_with_database) as client:
        body = (await client.get(f"/campaigns/{campaign_id}/outputs")).json()

    assert body["outputs"] == [{"filename": "Acme Corp.mp4", "size_bytes": len(b"staged-output")}]
    assert body["exportable_count"] == 1
    assert body["total_size_bytes"] == len(b"staged-output")


async def test_export_rejects_destination_inside_workspace(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
) -> None:
    export_dir = tmp_workspace.outputs / "nested-export"
    export_dir.mkdir(parents=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Inside workspace"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Acme Corp",
        )

    async with await client_for(app_with_database) as client:
        response = await client.post(
            f"/campaigns/{campaign_id}/export",
            json={"destination_path": str(export_dir)},
        )

    assert response.status_code == 422
    assert "outside the workspace" in response.json()["error"]["message"]


async def test_export_moves_files_and_clears_completed_jobs(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
    tmp_path: Path,
) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Export me"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        _asset, job, staged_path = _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Acme Corp",
        )
        job_id = job.id

    async with await client_for(app_with_database) as client:
        body = (
            await client.post(
                f"/campaigns/{campaign_id}/export",
                json={"destination_path": str(export_dir)},
            )
        ).json()

    assert body["moved_count"] == 1
    assert body["moved_filenames"] == ["Acme Corp.mp4"]
    assert body["conflicts"] == []
    assert body["failures"] == []
    assert (export_dir / "Acme Corp.mp4").read_bytes() == b"staged-output"
    assert not staged_path.exists()

    with database.session_factory() as session:
        remaining = session.scalars(select(RenderJob).where(RenderJob.id == job_id)).all()
        assert remaining == []
        campaign = session.get(Campaign, campaign_id)
        assert campaign is not None
        assert campaign.default_export_path == str(export_dir)
        settings = session.get(AppSettings, 1)
        assert settings is not None
        assert settings.default_export_path is None


async def test_export_refuses_overwrites_and_reports_conflicts(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
    tmp_path: Path,
) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    (export_dir / "Acme Corp.mp4").write_bytes(b"existing")

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Conflicts"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Acme Corp",
            sort_order=0,
        )
        _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Beta Inc",
            sort_order=1,
        )

    async with await client_for(app_with_database) as client:
        body = (
            await client.post(
                f"/campaigns/{campaign_id}/export",
                json={"destination_path": str(export_dir)},
            )
        ).json()

    assert body["moved_count"] == 1
    assert body["moved_filenames"] == ["Beta Inc.mp4"]
    assert body["conflicts"] == ["Acme Corp.mp4"]
    assert (export_dir / "Acme Corp.mp4").read_bytes() == b"existing"
    assert (export_dir / "Beta Inc.mp4").exists()
    assert (tmp_workspace.outputs / campaign_id / "Acme Corp.mp4").exists()

    with database.session_factory() as session:
        jobs = session.scalars(select(RenderJob).where(RenderJob.campaign_id == campaign_id)).all()
        assert len(jobs) == 1
        assert jobs[0].output_filename == "Acme Corp.mp4"


async def test_export_mid_batch_only_moves_completed_jobs(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
    tmp_path: Path,
) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Mid batch"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Done Corp",
            sort_order=0,
        )
        _asset, waiting_job, waiting_path = _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Waiting Corp",
            sort_order=1,
            status=JobStatus.ENCODING.value,
        )
        waiting_job_id = waiting_job.id

    async with await client_for(app_with_database) as client:
        body = (
            await client.post(
                f"/campaigns/{campaign_id}/export",
                json={"destination_path": str(export_dir)},
            )
        ).json()

    assert body["moved_count"] == 1
    assert body["moved_filenames"] == ["Done Corp.mp4"]
    assert waiting_path.exists()

    with database.session_factory() as session:
        waiting = session.get(RenderJob, waiting_job_id)
        assert waiting is not None
        assert waiting.status == JobStatus.ENCODING.value


async def test_export_leaves_failed_jobs_in_queue(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
    tmp_path: Path,
) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Failures"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Good Corp",
            sort_order=0,
        )
        failed = RenderJob(
            campaign_id=campaign_id,
            asset_id=None,
            job_type=JobType.VIDEO_RENDER.value,
            status=JobStatus.FAILED.value,
            queue_position=2,
            error_message="Encode failed",
        )
        session.add(failed)
        session.commit()
        failed_id = failed.id

    async with await client_for(app_with_database) as client:
        await client.post(
            f"/campaigns/{campaign_id}/export",
            json={"destination_path": str(export_dir)},
        )

    with database.session_factory() as session:
        failed = session.get(RenderJob, failed_id)
        assert failed is not None
        assert failed.status == JobStatus.FAILED.value


async def test_export_partial_move_failure_leaves_failed_row_and_file(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Partial"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="First Corp",
            sort_order=0,
        )
        _asset, failed_job, failed_path = _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Second Corp",
            sort_order=1,
        )
        failed_job_id = failed_job.id

    original_move = shutil.move
    call_count = {"n": 0}

    def flaky_move(src: str, dst: str) -> None:
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("disk full")
        original_move(src, dst)

    monkeypatch.setattr(
        "outreachos_backend.modules.video_composer.service.shutil.move",
        flaky_move,
    )

    async with await client_for(app_with_database) as client:
        response = await client.post(
            f"/campaigns/{campaign_id}/export",
            json={"destination_path": str(export_dir)},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["moved_count"] == 1
    assert body["moved_filenames"] == ["First Corp.mp4"]
    assert body["failures"] == [
        {"filename": "Second Corp.mp4", "reason": "disk full"},
    ]
    assert (export_dir / "First Corp.mp4").exists()
    assert failed_path.is_file()

    with database.session_factory() as session:
        remaining = session.scalars(
            select(RenderJob).where(RenderJob.campaign_id == campaign_id)
        ).all()
        assert len(remaining) == 1
        assert remaining[0].id == failed_job_id


async def test_export_clears_alpha_prepare_when_last_video_job_exports(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
    tmp_path: Path,
) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Alpha clear"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Only Corp",
            sort_order=1,
        )
        alpha_job = RenderJob(
            campaign_id=campaign_id,
            asset_id=None,
            job_type=JobType.ALPHA_PREPARE.value,
            status=JobStatus.COMPLETED.value,
            queue_position=0,
            finished_at="2026-01-01T00:00:00Z",
        )
        session.add(alpha_job)
        session.commit()
        alpha_job_id = alpha_job.id

    async with await client_for(app_with_database) as client:
        await client.post(
            f"/campaigns/{campaign_id}/export",
            json={"destination_path": str(export_dir)},
        )

    with database.session_factory() as session:
        assert session.get(RenderJob, alpha_job_id) is None
