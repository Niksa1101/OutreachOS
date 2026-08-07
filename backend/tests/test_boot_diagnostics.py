"""Boot-time diagnostics for packaged-only failure modes (ticket 29)."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from outreachos_backend.__main__ import _probe_ffmpeg
from outreachos_backend.core.boot import BootReport
from outreachos_backend.core.config import LaunchConfig
from outreachos_backend.core.workspace import WorkspaceLayout, prepare_workspace
from outreachos_backend.rendering.binaries import resolve_binaries
from tests.conftest import TEST_BOOT_ID

REPO_ROOT = Path(__file__).resolve().parents[2]
FFMPEG_DIR = REPO_ROOT / "vendor" / "ffmpeg"


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> WorkspaceLayout:
    return prepare_workspace(tmp_path / "workspace")


def _launch_config(ffmpeg_dir: Path | None) -> LaunchConfig:
    return LaunchConfig(
        workspace=Path("unused"),
        port=0,
        dev=False,
        log_level="INFO",
        ffmpeg_dir=ffmpeg_dir,
        app_version="0.1.0",
        take_over=False,
        allow_without_backup=False,
    )


def test_probe_ffmpeg_missing_directory_marks_degraded() -> None:
    report = BootReport(
        boot_id=TEST_BOOT_ID,
        workspace_path="/tmp/ws",
        boot_log_path="/tmp/boot.log",
        backend_log_path="/tmp/outreachos.log",
    )
    config = _launch_config(None)

    assert _probe_ffmpeg(config, report) is None
    assert report.status == "degraded"
    assert report.diagnostic_code == "ffmpeg_missing"
    assert report.detail is not None


def test_probe_ffmpeg_missing_binary_marks_degraded(tmp_path: Path) -> None:
    empty_dir = tmp_path / "ffmpeg"
    empty_dir.mkdir()

    report = BootReport(
        boot_id=TEST_BOOT_ID,
        workspace_path="/tmp/ws",
        boot_log_path="/tmp/boot.log",
        backend_log_path="/tmp/outreachos.log",
    )
    config = _launch_config(empty_dir)

    assert _probe_ffmpeg(config, report) is None
    assert report.status == "degraded"
    assert report.diagnostic_code == "ffmpeg_missing"
    assert "Missing FFmpeg binary" in (report.detail or "")


def test_probe_ffmpeg_unrunnable_binary_marks_degraded(tmp_path: Path) -> None:
    ffmpeg_dir = tmp_path / "ffmpeg"
    ffmpeg_dir.mkdir()
    (ffmpeg_dir / "ffmpeg.exe").write_bytes(b"not an executable")
    (ffmpeg_dir / "ffprobe.exe").write_bytes(b"not an executable")

    report = BootReport(
        boot_id=TEST_BOOT_ID,
        workspace_path="/tmp/ws",
        boot_log_path="/tmp/boot.log",
        backend_log_path="/tmp/outreachos.log",
    )
    config = _launch_config(ffmpeg_dir)

    assert _probe_ffmpeg(config, report) is None
    assert report.status == "degraded"
    assert report.diagnostic_code == "ffmpeg_unrunnable"


def test_probe_ffmpeg_skipped_when_already_degraded(tmp_path: Path) -> None:
    report = BootReport(
        boot_id=TEST_BOOT_ID,
        workspace_path="/tmp/ws",
        boot_log_path="/tmp/boot.log",
        backend_log_path="/tmp/outreachos.log",
        status="degraded",
        diagnostic_code="workspace_locked",
    )
    config = _launch_config(tmp_path / "missing")

    assert _probe_ffmpeg(config, report) is None
    assert report.diagnostic_code == "workspace_locked"


async def test_health_surfaces_ffmpeg_degraded(
    app: FastAPI,
    tmp_workspace: WorkspaceLayout,
    client: AsyncClient,
) -> None:
    report: BootReport = app.state.runtime.report
    report.status = "degraded"
    report.diagnostic_code = "ffmpeg_missing"
    report.detail = "Missing FFmpeg binary: C:/resources/ffmpeg/ffmpeg.exe"

    body = (await client.get("/health")).json()
    assert body["status"] == "degraded"
    assert body["diagnostic_code"] == "ffmpeg_missing"
    assert body["detail"] == report.detail


@pytest.mark.skipif(
    not (FFMPEG_DIR / "ffmpeg.exe").is_file(),
    reason="vendor/ffmpeg not present",
)
def test_probe_ffmpeg_ok_with_vendor_binaries() -> None:
    report = BootReport(
        boot_id=TEST_BOOT_ID,
        workspace_path="/tmp/ws",
        boot_log_path="/tmp/boot.log",
        backend_log_path="/tmp/outreachos.log",
    )
    config = _launch_config(FFMPEG_DIR)

    binaries = _probe_ffmpeg(config, report)
    assert binaries is not None
    assert report.status == "ok"
    assert resolve_binaries(FFMPEG_DIR).ffmpeg == binaries.ffmpeg
