"""Central validation service — PRD §6.6, DB.md §4.3."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.enums import AssetRole, ProbeStatus
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.models import MediaAsset
from outreachos_backend.modules.video_composer.validation import (
    ValidationIssueCode,
    ValidationSeverity,
    validate_campaign,
)
from outreachos_backend.rendering.process import run_tool
from tests.conftest import TEST_TOKEN

REPO_ROOT = Path(__file__).resolve().parents[2]
FFMPEG_DIR = REPO_ROOT / "vendor" / "ffmpeg"


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


@pytest.fixture(scope="session")
def ffmpeg_dir() -> Path:
    if not (FFMPEG_DIR / "ffmpeg.exe").is_file():
        pytest.skip("vendor/ffmpeg not present — run scripts/fetch-ffmpeg.ps1")
    return FFMPEG_DIR


def _make_video(
    ffmpeg_dir: Path,
    path: Path,
    *,
    size: str = "640x480",
    duration_s: float = 2.0,
    audio: bool = False,
) -> None:
    ffmpeg = ffmpeg_dir / "ffmpeg.exe"
    args = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration_s}:size={size}:rate=30",
    ]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_s}", "-c:a", "aac"]
    else:
        args += ["-an"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    run_tool(args, timeout_s=120.0)


def _talking_head(
    *,
    asset_id: str = "head-1",
    duration_ms: int = 5000,
    trim_start_ms: int = 0,
    trim_end_ms: int | None = None,
    file_missing: bool = False,
    probe_status: str = ProbeStatus.OK.value,
    probe_error: str | None = None,
) -> MediaAsset:
    return MediaAsset(
        id=asset_id,
        campaign_id="camp-1",
        role=AssetRole.TALKING_HEAD.value,
        source_path="C:/videos/head.mp4",
        source_filename="head.mp4",
        probe_status=probe_status,
        probe_error=probe_error,
        duration_ms=duration_ms,
        width=640,
        height=360,
        fps=30.0,
        video_codec="h264",
        has_audio=1,
        file_missing=1 if file_missing else 0,
        trim_start_ms=trim_start_ms,
        trim_end_ms=trim_end_ms if trim_end_ms is not None else duration_ms,
        focal_x=0.5,
        focal_y=0.5,
    )


def _recording(
    *,
    asset_id: str = "rec-1",
    company_name: str = "Acme Corp",
    source_filename: str = "acme_corp.mp4",
    duration_ms: int = 8000,
    width: int = 640,
    height: int = 360,
    file_missing: bool = False,
    probe_status: str = ProbeStatus.OK.value,
    probe_error: str | None = None,
    sort_order: int = 0,
    name_auto_suffixed: bool = False,
) -> MediaAsset:
    return MediaAsset(
        id=asset_id,
        campaign_id="camp-1",
        role=AssetRole.SCREEN_RECORDING.value,
        source_path=f"C:/videos/{source_filename}",
        source_filename=source_filename,
        company_name=company_name,
        output_basename=company_name,
        sort_order=sort_order,
        probe_status=probe_status,
        probe_error=probe_error,
        duration_ms=duration_ms if probe_status == ProbeStatus.OK.value else None,
        width=width if probe_status == ProbeStatus.OK.value else None,
        height=height if probe_status == ProbeStatus.OK.value else None,
        fps=30.0 if probe_status == ProbeStatus.OK.value else None,
        video_codec="h264" if probe_status == ProbeStatus.OK.value else None,
        has_audio=0 if probe_status == ProbeStatus.OK.value else None,
        file_missing=1 if file_missing else 0,
        name_auto_suffixed=1 if name_auto_suffixed else 0,
    )


def test_no_talking_head_is_blocking() -> None:
    result = validate_campaign(talking_head=None, recordings=[_recording()])

    codes = [issue.code for issue in result.issues]
    assert ValidationIssueCode.NO_TALKING_HEAD in codes
    assert result.can_generate is False
    assert result.generate_blocked_reason == "Assign a talking-head video before generating."


def test_no_recordings_is_blocking() -> None:
    result = validate_campaign(talking_head=_talking_head(), recordings=[])

    codes = [issue.code for issue in result.issues]
    assert ValidationIssueCode.NO_RECORDINGS in codes
    assert result.can_generate is False
    assert result.generate_blocked_reason == "Add at least one screen recording before generating."


def test_missing_recording_file_is_row_blocking_only() -> None:
    result = validate_campaign(
        talking_head=_talking_head(),
        recordings=[
            _recording(asset_id="rec-missing", file_missing=True),
            _recording(asset_id="rec-ok"),
        ],
    )

    missing = next(
        issue for issue in result.issues if issue.code == ValidationIssueCode.SOURCE_FILE_MISSING
    )
    assert missing.severity == ValidationSeverity.BLOCKING
    assert missing.asset_id == "rec-missing"
    assert result.can_generate is True
    assert result.renderable_recording_count == 1


def test_missing_talking_head_blocks_generate() -> None:
    result = validate_campaign(
        talking_head=_talking_head(file_missing=True),
        recordings=[_recording()],
    )

    head_issue = next(
        issue
        for issue in result.issues
        if issue.code == ValidationIssueCode.SOURCE_FILE_MISSING and issue.asset_id == "head-1"
    )
    assert head_issue.message == "The talking-head source file is missing."
    assert result.can_generate is False
    assert result.generate_blocked_reason == "The talking-head source file is missing."


def test_probe_failed_recording_is_row_blocking() -> None:
    result = validate_campaign(
        talking_head=_talking_head(),
        recordings=[
            _recording(
                asset_id="rec-bad",
                probe_status=ProbeStatus.FAILED.value,
                probe_error="That file is not a video.",
            )
        ],
    )

    failed = next(
        issue for issue in result.issues if issue.code == ValidationIssueCode.PROBE_FAILED
    )
    assert failed.asset_id == "rec-bad"
    assert failed.message == "That file is not a video."
    assert result.can_generate is False
    assert result.renderable_recording_count == 0


def test_shorter_than_talking_head_is_warning() -> None:
    result = validate_campaign(
        talking_head=_talking_head(duration_ms=5000),
        recordings=[_recording(duration_ms=3000)],
    )

    warning = next(
        issue
        for issue in result.issues
        if issue.code == ValidationIssueCode.RECORDING_SHORTER_THAN_TALKING_HEAD
    )
    assert warning.severity == ValidationSeverity.WARNING
    assert result.can_generate is True


def test_non_16_9_is_warning() -> None:
    result = validate_campaign(
        talking_head=_talking_head(),
        recordings=[_recording(width=640, height=480)],
    )

    warning = next(
        issue for issue in result.issues if issue.code == ValidationIssueCode.ASPECT_RATIO_NOT_16_9
    )
    assert warning.severity == ValidationSeverity.WARNING
    assert result.can_generate is True


def test_duplicate_company_name_suffix_is_warning() -> None:
    result = validate_campaign(
        talking_head=_talking_head(),
        recordings=[
            _recording(asset_id="rec-1", company_name="Acme Corp"),
            _recording(
                asset_id="rec-2",
                company_name="Acme Corp (2)",
                source_filename="acme_corp_final_v2.mp4",
                sort_order=1,
                name_auto_suffixed=True,
            ),
        ],
    )

    warnings = [
        issue for issue in result.issues if issue.code == ValidationIssueCode.DUPLICATE_COMPANY_NAME
    ]
    assert len(warnings) == 1
    assert warnings[0].asset_id == "rec-2"
    assert warnings[0].severity == ValidationSeverity.WARNING
    assert result.warning_count == 1


def test_ready_campaign_can_generate() -> None:
    result = validate_campaign(
        talking_head=_talking_head(),
        recordings=[_recording(width=640, height=360)],
    )

    assert result.can_generate is True
    assert result.generate_blocked_reason is None
    assert result.renderable_recording_count == 1
    assert result.warning_count == 0


async def client_for(app: FastAPI) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1/api/v1",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )


async def test_campaign_detail_includes_validation(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    head = tmp_path / "head.mp4"
    short = tmp_path / "acme.mp4"
    wide = tmp_path / "acme_dup.mp4"
    _make_video(ffmpeg_dir, head, size="640x360", duration_s=3.0, audio=True)
    _make_video(ffmpeg_dir, short, size="640x360", duration_s=1.0)
    _make_video(ffmpeg_dir, wide, size="640x480")

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Validate me"})).json()
        campaign_id = created["id"]
        await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(head)},
        )
        imported = (
            await client.post(
                f"/campaigns/{campaign_id}/recordings/import",
                json={"source_paths": [str(short), str(wide)]},
            )
        ).json()
        # Rename the second recording onto the first one's name. The server
        # resolves the collision to "Acme (2)" and has to warn about it — the
        # name no longer resembles the filename it was derived from, so this
        # only works because the suffix decision is persisted, not re-derived.
        await client.patch(
            f"/campaigns/{campaign_id}/recordings/{imported['added'][1]['id']}",
            json={"company_name": imported["added"][0]["company_name"]},
        )
        detail = (await client.get(f"/campaigns/{campaign_id}")).json()

    validation = detail["validation"]
    codes = {issue["code"] for issue in validation["issues"]}
    assert validation["can_generate"] is True
    assert validation["renderable_recording_count"] == 2
    assert ValidationIssueCode.RECORDING_SHORTER_THAN_TALKING_HEAD.value in codes
    assert ValidationIssueCode.ASPECT_RATIO_NOT_16_9.value in codes
    assert ValidationIssueCode.DUPLICATE_COMPANY_NAME.value in codes
    assert detail["status"] == "ready"


async def test_empty_campaign_status_is_draft(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Empty"})).json()

    assert created["status"] == "draft"
    assert created["validation"]["can_generate"] is False
    assert created["validation"]["generate_blocked_reason"] == (
        "Assign a talking-head video before generating."
    )


async def test_missing_source_reads_persisted_link_health(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    head = tmp_path / "head.mp4"
    recording = tmp_path / "demo.mp4"
    _make_video(ffmpeg_dir, head, size="640x360", audio=True)
    _make_video(ffmpeg_dir, recording, size="640x360")

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Missing"})).json()
        campaign_id = created["id"]
        await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(head)},
        )
        imported = (
            await client.post(
                f"/campaigns/{campaign_id}/recordings/import",
                json={"source_paths": [str(recording)]},
            )
        ).json()

    recording.unlink()

    async with await client_for(app_with_database) as client:
        detail = (await client.get(f"/campaigns/{campaign_id}")).json()

    recording_id = imported["added"][0]["id"]
    missing_issues = [
        issue
        for issue in detail["validation"]["issues"]
        if issue["code"] == ValidationIssueCode.SOURCE_FILE_MISSING.value
        and issue["asset_id"] == recording_id
    ]
    assert len(missing_issues) == 1
    assert detail["recordings"][0]["file_missing"] is True
    assert detail["validation"]["can_generate"] is False
    assert detail["validation"]["renderable_recording_count"] == 0


async def test_list_status_reflects_validation(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    head = tmp_path / "head.mp4"
    recording = tmp_path / "demo.mp4"
    _make_video(ffmpeg_dir, head, size="640x360", audio=True)
    _make_video(ffmpeg_dir, recording, size="640x360")

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Listed"})).json()
        campaign_id = created["id"]
        await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(head)},
        )
        await client.post(
            f"/campaigns/{campaign_id}/recordings/import",
            json={"source_paths": [str(recording)]},
        )
        listed = (await client.get("/campaigns")).json()

    assert listed["campaigns"][0]["status"] == "ready"
