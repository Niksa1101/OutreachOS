"""Settings routes — ticket 25."""

import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.models import AppSettings
from outreachos_backend.core.settings_service import (
    GLOBAL_QUEUE_LOCK_REASON,
    compute_cache_size_bytes,
)
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.models import Campaign, RenderJob
from tests.conftest import TEST_BOOT_ID, TEST_TOKEN


@pytest.fixture
def app_with_database(app: FastAPI, tmp_workspace: WorkspaceLayout) -> FastAPI:
    database = Database(tmp_workspace.database)
    outcome = migrate.run_migrations(database.engine, database.path)
    assert outcome.ok, outcome.detail
    migrate.heal_app_settings(database.engine)

    migrate.apply_outcome(app.state.runtime.report, outcome)
    app.state.database = database
    return app


async def client_for(app: FastAPI) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1/api/v1",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )


async def test_settings_returns_the_seeded_defaults(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        body = (await client.get("/settings")).json()

    assert body["quality_preset"] == "standard"
    assert body["encoder_override"] is None, "NULL means auto-detect (Tech.md §5.2)"
    assert body["boot_id"] == TEST_BOOT_ID
    assert body["cache_size_bytes"] == 0
    assert body["queue_busy"] is False


async def test_settings_reports_the_migration_head(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        body = (await client.get("/settings")).json()

    assert body["migration_head"] is not None
    assert body["backend_log_path"].endswith("outreachos.log")


async def test_settings_needs_the_token(app_with_database: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_database),
        base_url="http://127.0.0.1/api/v1",
    ) as client:
        assert (await client.get("/settings")).status_code == 401


async def test_a_degraded_backend_hands_out_no_session(app_with_database: FastAPI) -> None:
    app_with_database.state.runtime.report.status = "degraded"
    app_with_database.state.runtime.report.detail = "pretend the migration failed"

    async with await client_for(app_with_database) as client:
        response = await client.get("/settings")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "workspace_error"
    assert body["error"]["details"]["detail"] == "pretend the migration failed"


async def test_health_still_answers_while_degraded(app_with_database: FastAPI) -> None:
    app_with_database.state.runtime.report.status = "degraded"
    app_with_database.state.runtime.report.diagnostic_code = "migration_failed"

    async with await client_for(app_with_database) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["diagnostic_code"] == "migration_failed"


async def test_patch_settings_persists_quality_and_export_folder(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
) -> None:
    export_dir = tmp_workspace.root / "exports"
    export_dir.mkdir()

    async with await client_for(app_with_database) as client:
        response = await client.patch(
            "/settings",
            json={
                "quality_preset": "high",
                "default_export_path": str(export_dir),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["quality_preset"] == "high"
    assert body["default_export_path"] == str(export_dir.resolve())

    database = app_with_database.state.database
    with database.session_factory() as session:
        settings = session.query(AppSettings).filter(AppSettings.id == 1).one()
        assert settings.quality_preset == "high"
        assert settings.default_export_path == str(export_dir.resolve())


async def test_patch_settings_can_clear_encoder_override(app_with_database: FastAPI) -> None:
    database = app_with_database.state.database
    with database.session_factory() as session:
        settings = session.query(AppSettings).filter(AppSettings.id == 1).one()
        settings.encoder_override = "libx264"
        session.commit()

    async with await client_for(app_with_database) as client:
        response = await client.patch("/settings", json={"encoder_override": None})

    assert response.status_code == 200
    assert response.json()["encoder_override"] is None


async def test_patch_settings_rejects_unknown_encoder(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        response = await client.patch("/settings", json={"encoder_override": "h264_fake"})

    assert response.status_code == 422


async def test_clear_cache_frees_bytes_and_resets_campaign_alpha(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
) -> None:
    alpha_dir = tmp_workspace.cache / "alpha"
    alpha_dir.mkdir(parents=True, exist_ok=True)
    clip = alpha_dir / "abc123.mov"
    clip.write_bytes(b"x" * 4096)

    database = app_with_database.state.database
    campaign_id: str
    with database.session_factory() as session:
        campaign = Campaign(
            name="Cached",
            overlay_config='{"schema_version":1}',
            overlay_schema_version=1,
            alpha_cache_key="abc123",
            alpha_cache_path="cache/alpha/abc123.mov",
        )
        session.add(campaign)
        session.commit()
        campaign_id = campaign.id

    assert compute_cache_size_bytes(tmp_workspace.cache) == 4096

    async with await client_for(app_with_database) as client:
        response = await client.post("/settings/clear-cache")

    assert response.status_code == 200
    assert response.json()["bytes_freed"] == 4096
    assert not clip.exists()

    with database.session_factory() as session:
        refreshed = session.get(Campaign, campaign_id)
        assert refreshed is not None
        assert refreshed.alpha_cache_key is None
        assert refreshed.alpha_cache_path is None


async def test_detected_encoder_default_from_cached_probe(app_with_database: FastAPI) -> None:
    database = app_with_database.state.database
    with database.session_factory() as session:
        settings = session.query(AppSettings).filter(AppSettings.id == 1).one()
        settings.detected_encoders = json.dumps(["h264_qsv", "libx264"])
        settings.ffmpeg_version = "ffmpeg version n7.1.5 test"
        session.commit()

    async with await client_for(app_with_database) as client:
        body = (await client.get("/settings")).json()

    assert body["detected_encoder"] == "h264_qsv"


async def test_settings_reports_queue_busy_when_jobs_are_active(
    app_with_database: FastAPI,
) -> None:
    database = app_with_database.state.database
    with database.session_factory() as session:
        campaign = Campaign(
            name="Busy",
            overlay_config='{"schema_version":1}',
            overlay_schema_version=1,
        )
        session.add(campaign)
        session.flush()
        session.add(
            RenderJob(
                campaign_id=campaign.id,
                job_type="video_render",
                status="encoding",
                queue_position=1,
            )
        )
        session.commit()

    async with await client_for(app_with_database) as client:
        body = (await client.get("/settings")).json()

    assert body["queue_busy"] is True


async def test_patch_settings_rejects_quality_while_queue_busy(
    app_with_database: FastAPI,
) -> None:
    database = app_with_database.state.database
    with database.session_factory() as session:
        campaign = Campaign(
            name="Busy",
            overlay_config='{"schema_version":1}',
            overlay_schema_version=1,
        )
        session.add(campaign)
        session.flush()
        session.add(
            RenderJob(
                campaign_id=campaign.id,
                job_type="video_render",
                status="waiting",
                queue_position=1,
            )
        )
        session.commit()

    async with await client_for(app_with_database) as client:
        response = await client.patch("/settings", json={"quality_preset": "high"})

    assert response.status_code == 409
    assert response.json()["error"]["message"] == GLOBAL_QUEUE_LOCK_REASON


async def test_clear_cache_rejects_while_queue_busy(app_with_database: FastAPI) -> None:
    database = app_with_database.state.database
    with database.session_factory() as session:
        campaign = Campaign(
            name="Busy",
            overlay_config='{"schema_version":1}',
            overlay_schema_version=1,
        )
        session.add(campaign)
        session.flush()
        session.add(
            RenderJob(
                campaign_id=campaign.id,
                job_type="video_render",
                status="waiting",
                queue_position=1,
            )
        )
        session.commit()

    async with await client_for(app_with_database) as client:
        response = await client.post("/settings/clear-cache")

    assert response.status_code == 409
    assert response.json()["error"]["message"] == GLOBAL_QUEUE_LOCK_REASON
