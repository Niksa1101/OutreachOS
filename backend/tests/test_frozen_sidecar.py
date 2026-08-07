"""Smoke tests for the PyInstaller-frozen backend sidecar."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TextIO, cast

import httpx
import pytest

from outreachos_backend.core.control import CONTROL_PREFIX

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_DIR = REPO_ROOT / "backend" / "dist" / "outreachos-backend"
BACKEND_EXE = FROZEN_DIR / "outreachos-backend.exe"
RENDER_EXE = FROZEN_DIR / "outreachos-render.exe"
FFMPEG_DIR = REPO_ROOT / "vendor" / "ffmpeg"

# Windows-only packaging ticket; keep the module importable elsewhere.
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows sidecar packaging")


def _require_frozen_build() -> None:
    if not BACKEND_EXE.is_file():
        pytest.skip("Frozen sidecar not built — run pnpm build:sidecar")


def _read_control_line(stdout: TextIO | Any) -> dict[str, object]:
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        line = stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        text = line.decode("utf-8") if isinstance(line, bytes) else line
        if text.startswith(CONTROL_PREFIX):
            return cast(dict[str, object], json.loads(text[len(CONTROL_PREFIX) :].strip()))
    raise AssertionError("Timed out waiting for @@OOS control line from frozen sidecar")


@pytest.fixture(scope="module")
def ffmpeg_dir() -> Path:
    if not (FFMPEG_DIR / "ffmpeg.exe").is_file():
        pytest.skip("vendor/ffmpeg not present — run scripts/fetch-ffmpeg.ps1")
    return FFMPEG_DIR


def test_frozen_sidecar_boots_migrates_and_serves_health(
    tmp_path_factory: pytest.TempPathFactory,
    ffmpeg_dir: Path,
) -> None:
    _require_frozen_build()
    workspace = tmp_path_factory.mktemp("frozen-sidecar")
    token = "a" * 64
    boot_id = "frozen-smoke-boot"

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        [
            str(BACKEND_EXE),
            "--workspace",
            str(workspace),
            "--ffmpeg-dir",
            str(ffmpeg_dir),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None

    try:
        proc.stdin.write(json.dumps({"boot_id": boot_id, "token": token}).encode("utf-8"))
        proc.stdin.write(b"\n")
        proc.stdin.flush()

        control = _read_control_line(proc.stdout)
        port = control["port"]
        assert isinstance(port, int)
        assert control.get("boot_id") == boot_id

        deadline = time.monotonic() + 20.0
        last_body: dict[str, object] | None = None
        while time.monotonic() < deadline:
            try:
                response = httpx.get(
                    f"http://127.0.0.1:{port}/api/v1/health",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=2.0,
                )
            except httpx.HTTPError:
                time.sleep(0.1)
                continue
            if response.status_code == 200:
                last_body = response.json()
                break
            time.sleep(0.1)

        assert last_body is not None, "Frozen sidecar never returned /health 200"
        assert last_body["status"] == "ok"
        assert last_body["boot_id"] == boot_id
        assert last_body["migration_head"] is not None
        assert last_body["migration_current"] == last_body["migration_head"]
    finally:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        proc.wait(timeout=30)
        if proc.returncode not in (0, None):
            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            raise AssertionError(f"Frozen sidecar exited {proc.returncode}: {stderr}")


def test_frozen_render_cli_runs_batch(
    tmp_path_factory: pytest.TempPathFactory,
    ffmpeg_dir: Path,
) -> None:
    _require_frozen_build()
    if not RENDER_EXE.is_file():
        pytest.skip("outreachos-render.exe was not built")

    from tests.rendering.conftest import _ensure_fixtures

    fixture_root = tmp_path_factory.mktemp("frozen-render-fixtures")
    _ensure_fixtures(fixture_root, ffmpeg_dir)
    config_path = fixture_root / "batch.json"
    out_dir = tmp_path_factory.mktemp("frozen-render-out")

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    completed = subprocess.run(
        [
            str(RENDER_EXE),
            "--ffmpeg-dir",
            str(ffmpeg_dir),
            "render",
            "--config",
            str(config_path),
            "--out",
            str(out_dir),
            "--force-libx264",
            "--strict-version",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        creationflags=creationflags,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    outputs = sorted(out_dir.glob("*.mp4"))
    assert outputs, "Frozen render CLI produced no MP4 outputs"
