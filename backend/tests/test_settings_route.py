"""``GET /api/v1/settings`` — the first route with a database behind it.

Q90 keeps it read-only in P0: workspace path, versions, ``boot_id``, migration
head, log path. No "Change workspace" — that is P5, and shipping the button
before the kill-and-respawn path exists would be a dead control on the one
screen users go looking for it.

Q84 makes this also the first route that can 503, which is the behaviour worth
pinning down: **degraded means zero sessions handed out**, not "available but
flagged".
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.workspace import WorkspaceLayout
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


async def test_settings_reports_the_migration_head(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        body = (await client.get("/settings")).json()

    # Q90: the head is one of the five facts this page exists to show.
    assert body["migration_head"] is not None
    assert body["backend_log_path"].endswith("outreachos.log")


async def test_settings_needs_the_token(app_with_database: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_database),
        base_url="http://127.0.0.1/api/v1",
    ) as client:
        assert (await client.get("/settings")).status_code == 401


async def test_a_degraded_backend_hands_out_no_session(app_with_database: FastAPI) -> None:
    # Q84, stated as behaviour rather than as a comment: the dependency raises
    # *before* yielding, so there is no path by which the app reads or writes
    # against a schema it does not understand.
    app_with_database.state.runtime.report.status = "degraded"
    app_with_database.state.runtime.report.detail = "pretend the migration failed"

    async with await client_for(app_with_database) as client:
        response = await client.get("/settings")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "workspace_error"
    # The reason travels with it — the diagnostics screen shows this verbatim.
    assert body["error"]["details"]["detail"] == "pretend the migration failed"


async def test_health_still_answers_while_degraded(app_with_database: FastAPI) -> None:
    # Q113/Q104: `/health` never opens a session, which is precisely what lets
    # the diagnostics screen work when every DB route is refusing.
    app_with_database.state.runtime.report.status = "degraded"
    app_with_database.state.runtime.report.diagnostic_code = "migration_failed"

    async with await client_for(app_with_database) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["diagnostic_code"] == "migration_failed"
