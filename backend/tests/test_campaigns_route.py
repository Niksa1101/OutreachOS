"""``/api/v1/campaigns`` — list, create, read-one, rename, and delete."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.enums import AssetRole, ProbeStatus
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.models import Campaign, MediaAsset, RenderJob
from outreachos_backend.rendering.config import OverlayConfig
from outreachos_backend.rendering.process import run_tool
from tests.conftest import TEST_TOKEN

REPO_ROOT = Path(__file__).resolve().parents[2]
FFMPEG_DIR = REPO_ROOT / "vendor" / "ffmpeg"


@pytest.fixture(scope="session")
def ffmpeg_dir() -> Path:
    if not (FFMPEG_DIR / "ffmpeg.exe").is_file():
        pytest.skip("vendor/ffmpeg not present — run scripts/fetch-ffmpeg.ps1")
    return FFMPEG_DIR


def _make_video(ffmpeg_dir: Path, path: Path, *, audio: bool) -> None:
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
        "testsrc=duration=2:size=640x480:rate=30",
    ]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac"]
    else:
        args += ["-an"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    run_tool(args, timeout_s=120.0)


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


async def test_list_starts_empty(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        body = (await client.get("/campaigns")).json()

    assert body == {"campaigns": []}


async def test_create_returns_default_overlay_config(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        response = await client.post("/campaigns", json={})
        body = response.json()

    assert response.status_code == 201
    assert body["name"] == "Untitled campaign"
    assert body["recording_count"] == 0
    assert body["last_rendered_at"] is None
    assert body["status"] == "draft"
    assert body["overlay_schema_version"] == 1

    stored = OverlayConfig.model_validate_json(body["overlay_config"])
    assert stored == OverlayConfig()


async def test_create_accepts_a_custom_name(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        body = (await client.post("/campaigns", json={"name": "Acme outreach"})).json()

    assert body["name"] == "Acme outreach"


async def test_list_returns_created_campaigns(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        await client.post("/campaigns", json={"name": "First"})
        await client.post("/campaigns", json={"name": "Second"})
        body = (await client.get("/campaigns")).json()

    names = [campaign["name"] for campaign in body["campaigns"]]
    assert names == ["Second", "First"]


async def test_read_one_returns_a_campaign(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Lookup me"})).json()
        body = (await client.get(f"/campaigns/{created['id']}")).json()

    assert body["id"] == created["id"]
    assert body["name"] == "Lookup me"


async def test_read_one_404s_for_an_unknown_id(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        response = await client.get("/campaigns/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_rename_updates_the_campaign(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Before"})).json()
        body = (await client.patch(f"/campaigns/{created['id']}", json={"name": "After"})).json()

    assert body["name"] == "After"

    async with await client_for(app_with_database) as client:
        listed = (await client.get("/campaigns")).json()

    assert listed["campaigns"][0]["name"] == "After"


async def test_rename_404s_for_an_unknown_id(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        response = await client.patch("/campaigns/does-not-exist", json={"name": "Nope"})

    assert response.status_code == 404


async def test_campaigns_need_the_token(app_with_database: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_database),
        base_url="http://127.0.0.1/api/v1",
    ) as client:
        assert (await client.get("/campaigns")).status_code == 401


async def test_delete_preview_for_empty_campaign(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Empty"})).json()
        body = (await client.get(f"/campaigns/{created['id']}/delete-preview")).json()

    assert body["campaign_name"] == "Empty"
    assert body["asset_count"] == 0
    assert body["recording_count"] == 0
    assert body["talking_head_count"] == 0
    assert body["alpha_clip"] == {"present": False, "size_bytes": None}
    assert body["outputs"] == {"count": 0, "total_size_bytes": 0}


async def test_delete_preview_reports_workspace_files(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Loaded"})).json()
        campaign_id = created["id"]

    alpha_dir = tmp_workspace.cache / "alpha"
    alpha_dir.mkdir(parents=True, exist_ok=True)
    alpha_key = "abc123"
    alpha_clip = alpha_dir / f"{alpha_key}.mov"
    alpha_clip.write_bytes(b"alpha-bytes")

    output_dir = tmp_workspace.outputs / campaign_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "Acme Corp.mp4").write_bytes(b"0123456789")

    database = app_with_database.state.database
    with database.session_factory() as session:
        campaign = session.get(Campaign, campaign_id)
        assert campaign is not None
        campaign.alpha_cache_key = alpha_key
        session.commit()

    async with await client_for(app_with_database) as client:
        body = (await client.get(f"/campaigns/{campaign_id}/delete-preview")).json()

    assert body["alpha_clip"] == {"present": True, "size_bytes": len(b"alpha-bytes")}
    assert body["outputs"] == {"count": 1, "total_size_bytes": 10}


async def test_delete_removes_campaign_and_workspace_files_but_not_sources(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "outside-workspace" / "recording.mp4"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"source-recording")

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Delete me"})).json()
        campaign_id = created["id"]

    alpha_dir = tmp_workspace.cache / "alpha"
    alpha_dir.mkdir(parents=True, exist_ok=True)
    alpha_key = "deadbeef"
    alpha_clip = alpha_dir / f"{alpha_key}.mov"
    alpha_clip.write_bytes(b"cached-alpha")
    (alpha_dir / f"{alpha_key}.manifest.json").write_text("{}")

    output_dir = tmp_workspace.outputs / campaign_id
    output_dir.mkdir(parents=True, exist_ok=True)
    staged_output = output_dir / "Acme Corp.mp4"
    staged_output.write_bytes(b"staged-output")

    from outreachos_backend.modules.video_composer.models import MediaAsset

    database = app_with_database.state.database
    with database.session_factory() as session:
        campaign = session.get(Campaign, campaign_id)
        assert campaign is not None
        campaign.alpha_cache_key = alpha_key
        session.add(
            MediaAsset(
                campaign_id=campaign_id,
                role=AssetRole.SCREEN_RECORDING.value,
                source_path=str(source_file),
                source_filename=source_file.name,
                probe_status=ProbeStatus.OK.value,
            )
        )
        session.commit()

    async with await client_for(app_with_database) as client:
        response = await client.delete(f"/campaigns/{campaign_id}")
        assert response.status_code == 204
        listed = (await client.get("/campaigns")).json()
        assert listed["campaigns"] == []
        assert (await client.get(f"/campaigns/{campaign_id}")).status_code == 404

    assert source_file.is_file()
    assert not alpha_clip.is_file()
    assert not staged_output.is_file()
    assert not output_dir.exists()


async def test_delete_404s_for_an_unknown_id(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        response = await client.delete("/campaigns/does-not-exist")

    assert response.status_code == 404


async def test_assign_talking_head_probes_and_persists_metadata(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    video = tmp_path / "presenter.mp4"
    _make_video(ffmpeg_dir, video, audio=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "With head"})).json()
        response = await client.put(
            f"/campaigns/{created['id']}/talking-head",
            json={"source_path": str(video)},
        )
        body = response.json()

    assert response.status_code == 200
    talking_head = body["talking_head"]
    assert talking_head is not None
    assert talking_head["source_path"] == str(video.resolve())
    assert talking_head["source_filename"] == "presenter.mp4"
    assert talking_head["duration_ms"] == 2000
    assert talking_head["width"] == 640
    assert talking_head["height"] == 480
    assert talking_head["fps"] == pytest.approx(30.0)
    assert talking_head["video_codec"] == "h264"
    assert talking_head["has_audio"] is True
    assert talking_head["trim_start_ms"] == 0
    assert talking_head["trim_end_ms"] == 2000
    assert talking_head["focal_x"] == 0.5
    assert talking_head["focal_y"] == 0.5


async def test_assign_talking_head_replaces_the_existing_one(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    _make_video(ffmpeg_dir, first, audio=True)
    _make_video(ffmpeg_dir, second, audio=False)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Replace"})).json()
        campaign_id = created["id"]
        first_body = (
            await client.put(
                f"/campaigns/{campaign_id}/talking-head",
                json={"source_path": str(first)},
            )
        ).json()
        second_body = (
            await client.put(
                f"/campaigns/{campaign_id}/talking-head",
                json={"source_path": str(second)},
            )
        ).json()
        listed = (await client.get(f"/campaigns/{campaign_id}")).json()

    assert first_body["talking_head"]["source_filename"] == "first.mp4"
    assert second_body["talking_head"]["source_filename"] == "second.mp4"
    assert second_body["talking_head"]["has_audio"] is False
    assert listed["talking_head"]["source_filename"] == "second.mp4"

    database = app_with_database.state.database
    with database.session_factory() as session:
        heads = session.scalars(
            select(MediaAsset).where(
                MediaAsset.campaign_id == campaign_id,
                MediaAsset.role == AssetRole.TALKING_HEAD.value,
            )
        ).all()
        assert len(heads) == 1
        assert heads[0].source_filename == "second.mp4"


async def test_assign_talking_head_rejects_a_missing_file(
    app_with_database: FastAPI,
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.mp4"

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Missing"})).json()
        response = await client.put(
            f"/campaigns/{created['id']}/talking-head",
            json={"source_path": str(missing)},
        )
        detail = (await client.get(f"/campaigns/{created['id']}")).json()

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "That file could not be found."
    assert detail["talking_head"] is None


async def test_assign_talking_head_rejects_a_non_video_file(
    app_with_database: FastAPI,
    tmp_path: Path,
) -> None:
    text_file = tmp_path / "notes.txt"
    text_file.write_text("not a video", encoding="utf-8")

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Text"})).json()
        response = await client.put(
            f"/campaigns/{created['id']}/talking-head",
            json={"source_path": str(text_file)},
        )
        detail = (await client.get(f"/campaigns/{created['id']}")).json()

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "That file could not be read as a video."
    assert detail["talking_head"] is None


async def test_import_recordings_probes_and_names_from_filenames(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    first = tmp_path / "acme_corp.mp4"
    second = tmp_path / "acme-corp_final_v2.mp4"
    _make_video(ffmpeg_dir, first, audio=True)
    _make_video(ffmpeg_dir, second, audio=False)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Batch"})).json()
        response = await client.post(
            f"/campaigns/{created['id']}/recordings/import",
            json={"source_paths": [str(first), str(second)]},
        )
        body = response.json()
        detail = (await client.get(f"/campaigns/{created['id']}")).json()

    assert response.status_code == 200
    assert body["recording_count"] == 2
    assert body["rejected"] == []
    assert body["failed"] == []

    added = body["added"]
    assert len(added) == 2
    assert added[0]["company_name"] == "Acme Corp"
    assert added[0]["output_basename"] == "Acme Corp"
    assert added[0]["duration_ms"] == 2000
    assert added[0]["width"] == 640
    assert added[0]["height"] == 480
    assert added[0]["probe_status"] == "ok"
    assert added[0]["has_audio"] is True

    assert added[1]["company_name"] == "Acme Corp (2)"
    assert added[1]["output_basename"] == "Acme Corp (2)"
    assert added[1]["has_audio"] is False

    assert len(detail["recordings"]) == 2
    assert detail["recording_count"] == 2


async def test_import_recordings_rejects_duplicate_source_paths(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    video = tmp_path / "stripe_walkthrough.mp4"
    _make_video(ffmpeg_dir, video, audio=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Dupes"})).json()
        campaign_id = created["id"]
        first = await client.post(
            f"/campaigns/{campaign_id}/recordings/import",
            json={"source_paths": [str(video)]},
        )
        second = await client.post(
            f"/campaigns/{campaign_id}/recordings/import",
            json={"source_paths": [str(video)]},
        )
        first_body = first.json()
        second_body = second.json()

    assert first_body["recording_count"] == 1
    assert second_body["recording_count"] == 1
    assert second_body["rejected"] == [
        {
            "source_path": str(video.resolve()),
            "message": "That file is already in this campaign.",
        }
    ]


async def test_import_recordings_reports_probe_failures_without_blocking(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    good = tmp_path / "notion_demo.mp4"
    bad = tmp_path / "broken.txt"
    _make_video(ffmpeg_dir, good, audio=True)
    bad.write_text("not a video", encoding="utf-8")

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Mixed"})).json()
        body = (
            await client.post(
                f"/campaigns/{created['id']}/recordings/import",
                json={"source_paths": [str(good), str(bad)]},
            )
        ).json()

    assert body["recording_count"] == 2
    assert len(body["added"]) == 2
    assert body["added"][0]["probe_status"] == "ok"
    assert body["added"][1]["probe_status"] == "failed"
    assert body["failed"] == [
        {
            "source_path": str(bad.resolve()),
            "message": "That file could not be read as a video.",
        }
    ]


async def test_update_recording_renames_and_resolves_collisions(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    first = tmp_path / "acme_corp.mp4"
    second = tmp_path / "beta_inc.mp4"
    _make_video(ffmpeg_dir, first, audio=True)
    _make_video(ffmpeg_dir, second, audio=False)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Rename"})).json()
        campaign_id = created["id"]
        imported = (
            await client.post(
                f"/campaigns/{campaign_id}/recordings/import",
                json={"source_paths": [str(first), str(second)]},
            )
        ).json()
        first_id = imported["added"][0]["id"]
        second_id = imported["added"][1]["id"]

        body = (
            await client.patch(
                f"/campaigns/{campaign_id}/recordings/{second_id}",
                json={"company_name": "Acme Corp"},
            )
        ).json()
        detail = (await client.get(f"/campaigns/{campaign_id}")).json()

    assert body["company_name"] == "Acme Corp (2)"
    assert body["output_basename"] == "Acme Corp (2)"
    assert detail["recordings"][1]["output_basename"] == "Acme Corp (2)"

    async with await client_for(app_with_database) as client:
        unchanged = (
            await client.patch(
                f"/campaigns/{campaign_id}/recordings/{first_id}",
                json={"company_name": "Acme Corp"},
            )
        ).json()

    assert unchanged["company_name"] == "Acme Corp"
    assert unchanged["output_basename"] == "Acme Corp"


async def test_update_recording_rejects_empty_company_name(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    video = tmp_path / "stripe_walkthrough.mp4"
    _make_video(ffmpeg_dir, video, audio=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Empty name"})).json()
        campaign_id = created["id"]
        imported = (
            await client.post(
                f"/campaigns/{campaign_id}/recordings/import",
                json={"source_paths": [str(video)]},
            )
        ).json()
        recording_id = imported["added"][0]["id"]
        response = await client.patch(
            f"/campaigns/{campaign_id}/recordings/{recording_id}",
            json={"company_name": "   "},
        )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "A company name cannot be empty."


async def test_delete_recording_removes_reference_but_not_source_file(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    video = tmp_path / "keep_me.mp4"
    _make_video(ffmpeg_dir, video, audio=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Delete row"})).json()
        campaign_id = created["id"]
        imported = (
            await client.post(
                f"/campaigns/{campaign_id}/recordings/import",
                json={"source_paths": [str(video)]},
            )
        ).json()
        recording_id = imported["added"][0]["id"]
        response = await client.delete(f"/campaigns/{campaign_id}/recordings/{recording_id}")
        detail = (await client.get(f"/campaigns/{campaign_id}")).json()

    assert response.status_code == 204
    assert detail["recordings"] == []
    assert detail["recording_count"] == 0
    assert video.is_file()


async def test_delete_recording_404s_for_unknown_id(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Missing"})).json()
        response = await client.delete(
            f"/campaigns/{created['id']}/recordings/does-not-exist",
        )

    assert response.status_code == 404


async def test_get_campaign_detects_missing_recording_and_talking_head(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    head = tmp_path / "presenter.mp4"
    recording = tmp_path / "demo.mp4"
    _make_video(ffmpeg_dir, head, audio=True)
    _make_video(ffmpeg_dir, recording, audio=False)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Health"})).json()
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

    head.unlink()
    recording.unlink()

    async with await client_for(app_with_database) as client:
        detail = (await client.get(f"/campaigns/{campaign_id}")).json()

    assert detail["talking_head"]["file_missing"] is True
    assert detail["recordings"][0]["file_missing"] is True
    assert detail["recordings"][0]["id"] == imported["added"][0]["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        assets = session.scalars(
            select(MediaAsset).where(MediaAsset.campaign_id == campaign_id)
        ).all()
        assert all(asset.file_missing == 1 for asset in assets)
        assert all(asset.last_verified_at is not None for asset in assets)


async def test_get_campaign_clears_missing_flag_when_file_returns(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    video = tmp_path / "returns.mp4"
    _make_video(ffmpeg_dir, video, audio=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Returns"})).json()
        campaign_id = created["id"]
        imported = (
            await client.post(
                f"/campaigns/{campaign_id}/recordings/import",
                json={"source_paths": [str(video)]},
            )
        ).json()
        recording_id = imported["added"][0]["id"]

    video.unlink()

    async with await client_for(app_with_database) as client:
        missing = (await client.get(f"/campaigns/{campaign_id}")).json()
        assert missing["recordings"][0]["file_missing"] is True

    _make_video(ffmpeg_dir, video, audio=True)

    async with await client_for(app_with_database) as client:
        restored = (await client.get(f"/campaigns/{campaign_id}")).json()

    assert restored["recordings"][0]["id"] == recording_id
    assert restored["recordings"][0]["file_missing"] is False


async def test_relocate_recording_repoints_probes_and_clears_missing(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    original = tmp_path / "old_path.mp4"
    relocated = tmp_path / "new_path.mp4"
    _make_video(ffmpeg_dir, original, audio=True)
    original.unlink()

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Relocate"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        asset = MediaAsset(
            campaign_id=campaign_id,
            role=AssetRole.SCREEN_RECORDING.value,
            source_path=str(original.resolve()),
            source_filename=original.name,
            company_name="Acme Corp",
            output_basename="Acme Corp",
            sort_order=0,
            probe_status=ProbeStatus.OK.value,
            duration_ms=2000,
            width=640,
            height=480,
            fps=30.0,
            video_codec="h264",
            has_audio=1,
            file_missing=1,
            last_verified_at="2020-01-01T00:00:00Z",
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        asset_id = asset.id

    _make_video(ffmpeg_dir, relocated, audio=False)

    async with await client_for(app_with_database) as client:
        missing = (await client.get(f"/campaigns/{campaign_id}")).json()
        assert missing["recordings"][0]["file_missing"] is True

        response = await client.put(
            f"/campaigns/{campaign_id}/assets/{asset_id}/relocate",
            json={"source_path": str(relocated)},
        )
        body = response.json()

    assert response.status_code == 200
    recording = body["recordings"][0]
    assert recording["file_missing"] is False
    assert recording["source_path"] == str(relocated.resolve())
    assert recording["source_filename"] == "new_path.mp4"
    assert recording["probe_status"] == "ok"
    assert recording["has_audio"] is False


async def test_relocate_rejects_unreadable_file_and_keeps_missing_state(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    original = tmp_path / "gone.mp4"
    bad = tmp_path / "notes.txt"
    _make_video(ffmpeg_dir, original, audio=True)
    original.unlink()
    bad.write_text("not a video", encoding="utf-8")

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Reject"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        asset = MediaAsset(
            campaign_id=campaign_id,
            role=AssetRole.SCREEN_RECORDING.value,
            source_path=str(original.resolve()),
            source_filename=original.name,
            company_name="Acme Corp",
            output_basename="Acme Corp",
            sort_order=0,
            probe_status=ProbeStatus.OK.value,
            file_missing=1,
            last_verified_at="2020-01-01T00:00:00Z",
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        asset_id = asset.id

    async with await client_for(app_with_database) as client:
        response = await client.put(
            f"/campaigns/{campaign_id}/assets/{asset_id}/relocate",
            json={"source_path": str(bad)},
        )
        detail = (await client.get(f"/campaigns/{campaign_id}")).json()

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "That file could not be read as a video."
    assert detail["recordings"][0]["file_missing"] is True
    assert detail["recordings"][0]["source_filename"] == original.name


async def test_relocate_rejects_path_already_used_by_another_row(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    _make_video(ffmpeg_dir, first, audio=True)
    _make_video(ffmpeg_dir, second, audio=False)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Dupe relocate"})).json()
        campaign_id = created["id"]
        imported = (
            await client.post(
                f"/campaigns/{campaign_id}/recordings/import",
                json={"source_paths": [str(first), str(second)]},
            )
        ).json()
        missing_id = imported["added"][0]["id"]

    first.unlink()

    async with await client_for(app_with_database) as client:
        await client.get(f"/campaigns/{campaign_id}")
        response = await client.put(
            f"/campaigns/{campaign_id}/assets/{missing_id}/relocate",
            json={"source_path": str(second)},
        )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "That file is already in this campaign."


async def test_relocate_talking_head_clears_missing_flag(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    original = tmp_path / "old_head.mp4"
    relocated = tmp_path / "new_head.mp4"
    _make_video(ffmpeg_dir, original, audio=True)
    original.unlink()

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Head relocate"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        asset = MediaAsset(
            campaign_id=campaign_id,
            role=AssetRole.TALKING_HEAD.value,
            source_path=str(original.resolve()),
            source_filename=original.name,
            probe_status=ProbeStatus.OK.value,
            duration_ms=2000,
            width=640,
            height=480,
            fps=30.0,
            video_codec="h264",
            has_audio=1,
            file_missing=1,
            last_verified_at="2020-01-01T00:00:00Z",
            trim_start_ms=0,
            trim_end_ms=2000,
            focal_x=0.5,
            focal_y=0.5,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        asset_id = asset.id

    _make_video(ffmpeg_dir, relocated, audio=False)

    async with await client_for(app_with_database) as client:
        response = await client.put(
            f"/campaigns/{campaign_id}/assets/{asset_id}/relocate",
            json={"source_path": str(relocated)},
        )
        body = response.json()

    assert response.status_code == 200
    talking_head = body["talking_head"]
    assert talking_head is not None
    assert talking_head["file_missing"] is False
    assert talking_head["source_filename"] == "new_head.mp4"
    assert talking_head["has_audio"] is False


async def test_duplicate_campaign_without_talking_head(
    app_with_database: FastAPI,
) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Template"})).json()
        response = await client.post(f"/campaigns/{created['id']}/duplicate")
        body = response.json()

    assert response.status_code == 201
    assert body["id"] != created["id"]
    assert body["name"] == "Template (2)"
    assert body["recording_count"] == 0
    assert body["recordings"] == []
    assert body["talking_head"] is None
    assert body["last_rendered_at"] is None
    assert body["overlay_config"] == created["overlay_config"]
    assert body["overlay_schema_version"] == created["overlay_schema_version"]


async def test_duplicate_campaign_copies_talking_head_and_overlay(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    video = tmp_path / "presenter.mp4"
    recording = tmp_path / "screen.mp4"
    _make_video(ffmpeg_dir, video, audio=True)
    _make_video(ffmpeg_dir, recording, audio=False)

    custom_overlay = OverlayConfig(anchor="top_left", opacity=0.75)
    overlay_json = custom_overlay.model_dump_json()

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Source"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        campaign = session.get(Campaign, campaign_id)
        assert campaign is not None
        campaign.overlay_config = overlay_json
        campaign.quality_override = "high"
        campaign.alpha_cache_key = "cached-alpha"
        campaign.alpha_cache_path = "cache/alpha/cached-alpha.mov"
        session.commit()

    async with await client_for(app_with_database) as client:
        await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(video)},
        )
        await client.post(
            f"/campaigns/{campaign_id}/recordings/import",
            json={"source_paths": [str(recording)]},
        )

    with database.session_factory() as session:
        head = session.scalar(
            select(MediaAsset).where(
                MediaAsset.campaign_id == campaign_id,
                MediaAsset.role == AssetRole.TALKING_HEAD.value,
            )
        )
        assert head is not None
        head.trim_start_ms = 250
        head.trim_end_ms = 1750
        head.focal_x = 0.25
        head.focal_y = 0.75
        head.last_rendered_at = "2026-01-01T00:00:00Z"
        head.last_rendered_cache_key = "render-key"
        session.add(
            RenderJob(
                campaign_id=campaign_id,
                asset_id=head.id,
                job_type="video_render",
                status="waiting",
                queue_position=1,
            )
        )
        session.commit()

    async with await client_for(app_with_database) as client:
        response = await client.post(f"/campaigns/{campaign_id}/duplicate")
        duplicate = response.json()
        original = (await client.get(f"/campaigns/{campaign_id}")).json()

    assert response.status_code == 201
    assert duplicate["name"] == "Source (2)"
    assert duplicate["recording_count"] == 0
    assert duplicate["recordings"] == []
    assert duplicate["last_rendered_at"] is None
    assert duplicate["overlay_config"] == overlay_json
    assert duplicate["overlay_schema_version"] == custom_overlay.schema_version

    duplicate_head = duplicate["talking_head"]
    assert duplicate_head is not None
    assert duplicate_head["id"] != original["talking_head"]["id"]
    assert duplicate_head["source_path"] == str(video.resolve())
    assert duplicate_head["trim_start_ms"] == 250
    assert duplicate_head["trim_end_ms"] == 1750
    assert duplicate_head["focal_x"] == 0.25
    assert duplicate_head["focal_y"] == 0.75

    with database.session_factory() as session:
        duplicate_campaign = session.get(Campaign, duplicate["id"])
        assert duplicate_campaign is not None
        assert duplicate_campaign.alpha_cache_key is None
        assert duplicate_campaign.alpha_cache_path is None
        assert duplicate_campaign.quality_override == "high"

        duplicate_assets = session.scalars(
            select(MediaAsset).where(MediaAsset.campaign_id == duplicate["id"])
        ).all()
        assert len(duplicate_assets) == 1
        assert duplicate_assets[0].last_rendered_at is None
        assert duplicate_assets[0].last_rendered_cache_key is None

        duplicate_jobs = session.scalars(
            select(RenderJob).where(RenderJob.campaign_id == duplicate["id"])
        ).all()
        assert duplicate_jobs == []

        source_jobs = session.scalars(
            select(RenderJob).where(RenderJob.campaign_id == campaign_id)
        ).all()
        assert len(source_jobs) == 1


async def test_duplicate_campaign_disambiguates_existing_names(
    app_with_database: FastAPI,
) -> None:
    async with await client_for(app_with_database) as client:
        first = (await client.post("/campaigns", json={"name": "Acme"})).json()
        await client.post("/campaigns", json={"name": "Acme (2)"})
        duplicate = (await client.post(f"/campaigns/{first['id']}/duplicate")).json()

    assert duplicate["name"] == "Acme (3)"


async def test_duplicate_campaign_edits_do_not_affect_original(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    video = tmp_path / "presenter.mp4"
    _make_video(ffmpeg_dir, video, audio=True)

    custom_overlay = OverlayConfig(anchor="bottom_left")
    overlay_json = custom_overlay.model_dump_json()

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Original"})).json()
        campaign_id = created["id"]
        await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(video)},
        )

    database = app_with_database.state.database
    with database.session_factory() as session:
        campaign = session.get(Campaign, campaign_id)
        assert campaign is not None
        campaign.overlay_config = overlay_json
        session.commit()

    async with await client_for(app_with_database) as client:
        duplicate = (await client.post(f"/campaigns/{campaign_id}/duplicate")).json()

    with database.session_factory() as session:
        duplicate_campaign = session.get(Campaign, duplicate["id"])
        assert duplicate_campaign is not None
        duplicate_campaign.overlay_config = OverlayConfig(anchor="top_right").model_dump_json()
        duplicate_campaign.name = "Edited duplicate"

        duplicate_head = session.scalar(
            select(MediaAsset).where(
                MediaAsset.campaign_id == duplicate["id"],
                MediaAsset.role == AssetRole.TALKING_HEAD.value,
            )
        )
        assert duplicate_head is not None
        duplicate_head.trim_start_ms = 500
        duplicate_head.focal_x = 0.1
        session.commit()

    async with await client_for(app_with_database) as client:
        original = (await client.get(f"/campaigns/{campaign_id}")).json()

    assert original["name"] == "Original"
    stored = OverlayConfig.model_validate_json(original["overlay_config"])
    assert stored.anchor == "bottom_left"
    assert original["talking_head"]["trim_start_ms"] == 0
    assert original["talking_head"]["focal_x"] == 0.5


async def test_duplicate_campaign_404s_for_an_unknown_id(
    app_with_database: FastAPI,
) -> None:
    async with await client_for(app_with_database) as client:
        response = await client.post("/campaigns/does-not-exist/duplicate")

    assert response.status_code == 404


async def test_preview_frame_with_no_recordings_returns_placeholder(
    app_with_database: FastAPI,
) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Empty"})).json()
        response = await client.get(f"/campaigns/{created['id']}/preview-frame")
        body = response.json()

    assert response.status_code == 200
    assert body == {"available": False, "frame_path": None, "error": None}


async def test_preview_frame_extracts_and_caches_the_first_recording(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    first = tmp_path / "acme_corp.mp4"
    second = tmp_path / "beta_inc.mp4"
    _make_video(ffmpeg_dir, first, audio=True)
    _make_video(ffmpeg_dir, second, audio=False)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Preview"})).json()
        campaign_id = created["id"]
        await client.post(
            f"/campaigns/{campaign_id}/recordings/import",
            json={"source_paths": [str(first), str(second)]},
        )

        first_response = await client.get(f"/campaigns/{campaign_id}/preview-frame")
        first_body = first_response.json()

    assert first_response.status_code == 200
    assert first_body["available"] is True
    assert first_body["error"] is None
    frame_path = Path(first_body["frame_path"])
    assert frame_path.is_file()
    assert frame_path.is_relative_to(tmp_workspace.cache / "frames")
    first_mtime = frame_path.stat().st_mtime_ns

    async with await client_for(app_with_database) as client:
        second_response = await client.get(f"/campaigns/{campaign_id}/preview-frame")
        second_body = second_response.json()

    # Same cache key, same file, and — the point of the cache — not rewritten.
    assert second_body["frame_path"] == first_body["frame_path"]
    assert frame_path.stat().st_mtime_ns == first_mtime


async def test_preview_frame_reextracts_when_the_first_recording_is_replaced(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    original = tmp_path / "acme_corp.mp4"
    replacement = tmp_path / "new_recording.mp4"
    _make_video(ffmpeg_dir, original, audio=True)
    _make_video(ffmpeg_dir, replacement, audio=False)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Reextract"})).json()
        campaign_id = created["id"]
        imported = (
            await client.post(
                f"/campaigns/{campaign_id}/recordings/import",
                json={"source_paths": [str(original)]},
            )
        ).json()
        recording_id = imported["added"][0]["id"]

        before = (await client.get(f"/campaigns/{campaign_id}/preview-frame")).json()

        await client.put(
            f"/campaigns/{campaign_id}/assets/{recording_id}/relocate",
            json={"source_path": str(replacement)},
        )

        after = (await client.get(f"/campaigns/{campaign_id}/preview-frame")).json()

    assert before["available"] is True
    assert after["available"] is True
    # Relocating changes the source's stat fingerprint, so the content-addressed
    # cache key changes too — no explicit invalidation call needed.
    assert after["frame_path"] != before["frame_path"]


async def test_preview_frame_degrades_when_the_first_recording_cannot_be_probed(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    bad = tmp_path / "not_a_video.txt"
    bad.write_text("not a video", encoding="utf-8")

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Bad first"})).json()
        campaign_id = created["id"]
        await client.post(
            f"/campaigns/{campaign_id}/recordings/import",
            json={"source_paths": [str(bad)]},
        )

        response = await client.get(f"/campaigns/{campaign_id}/preview-frame")
        body = response.json()

    assert response.status_code == 200
    assert body["available"] is False
    assert body["frame_path"] is None
    assert body["error"] == "That file could not be read as a video."


async def test_import_rejects_talking_head_path_instead_of_500(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    video = tmp_path / "presenter.mp4"
    _make_video(ffmpeg_dir, video, audio=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Cross-role dupe"})).json()
        campaign_id = created["id"]
        await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(video)},
        )
        response = await client.post(
            f"/campaigns/{campaign_id}/recordings/import",
            json={"source_paths": [str(video)]},
        )
        body = response.json()

    assert response.status_code == 200
    assert body["recording_count"] == 0
    assert body["rejected"] == [
        {
            "source_path": str(video.resolve()),
            "message": "That file is already in this campaign.",
        }
    ]
