"""Shared fixtures.

The app is exercised through the real ASGI stack — middleware, dependency tree,
exception handlers — rather than by calling route functions directly. The
things most likely to break in P0 (CORS, the token dependency, the error
envelope, trailing-slash handling) all live in that stack and none of them are
reachable from a direct call.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from outreachos_backend.core.app import create_app
from outreachos_backend.core.boot import BootReport, Runtime
from outreachos_backend.core.events import EventBus
from outreachos_backend.core.workspace import WorkspaceLayout, prepare_workspace

TEST_TOKEN = "a" * 64
TEST_BOOT_ID = "test-boot-0001"


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> WorkspaceLayout:
    """A real directory on disk with the real layout.

    Q61: a real temp dir and file-backed SQLite, never `:memory:`. The failures
    worth catching on Windows — path handling, file locking, log rotation while
    another handle is open — are exactly the ones an in-memory database cannot
    reproduce.
    """
    return prepare_workspace(tmp_path / "workspace")


@pytest.fixture
def app(tmp_workspace: WorkspaceLayout) -> FastAPI:
    application = create_app(dev=False)

    report = BootReport(
        boot_id=TEST_BOOT_ID,
        workspace_path=str(tmp_workspace.root),
        boot_log_path=str(tmp_workspace.root / "boot.log"),
        backend_log_path=str(tmp_workspace.log_file),
        app_version="0.1.0",
    )

    application.state.event_bus = EventBus(boot_id=TEST_BOOT_ID)
    application.state.runtime = Runtime(report=report, token=TEST_TOKEN, dev=False)

    return application


async def _client(app: FastAPI, headers: dict[str, str]) -> AsyncIterator[AsyncClient]:
    # `ASGITransport` does not run the lifespan, and the one thing the lifespan
    # does is hand the bus its event loop. Doing it here directly is honest
    # about that and avoids a test-only dependency for a single line.
    app.state.event_bus.attach_loop(asyncio.get_running_loop())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1/api/v1",
        headers=headers,
    ) as instance:
        yield instance


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async for instance in _client(app, {"Authorization": f"Bearer {TEST_TOKEN}"}):
        yield instance


@pytest.fixture
async def anonymous_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async for instance in _client(app, {}):
        yield instance
