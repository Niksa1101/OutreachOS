"""``/api/v1/campaigns`` — list, create, read-one, rename, and delete."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.enums import AssetRole, JobStatus, JobType, ProbeStatus
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.models import Campaign, MediaAsset, RenderJob
from outreachos_backend.rendering.config import OverlayConfig, SizeConfig
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


async def test_update_overlay_persists_the_config(app_with_database: FastAPI) -> None:
    overlay = OverlayConfig(anchor="top_left", size=SizeConfig(width=300, height=300))

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={})).json()
        response = await client.put(
            f"/campaigns/{created['id']}/overlay",
            json=overlay.model_dump(mode="json"),
        )
        body = response.json()

    assert response.status_code == 200
    stored = OverlayConfig.model_validate_json(body["overlay_config"])
    assert stored.anchor == "top_left"
    assert stored.size.width == 300
    assert stored.size.height == 300

    async with await client_for(app_with_database) as client:
        refetched = (await client.get(f"/campaigns/{created['id']}")).json()

    assert refetched["overlay_config"] == body["overlay_config"]


async def test_update_overlay_clamps_off_frame_values_server_side(
    app_with_database: FastAPI,
) -> None:
    overlay = OverlayConfig(anchor="bottom_right", size=SizeConfig(width=5000, height=5000))

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={})).json()
        body = (
            await client.put(
                f"/campaigns/{created['id']}/overlay",
                json=overlay.model_dump(mode="json"),
            )
        ).json()

    stored = OverlayConfig.model_validate_json(body["overlay_config"])
    assert stored.size.width == 1920
    assert stored.size.height == 1080


async def test_update_overlay_404s_for_an_unknown_id(app_with_database: FastAPI) -> None:
    overlay = OverlayConfig()

    async with await client_for(app_with_database) as client:
        response = await client.put(
            "/campaigns/does-not-exist/overlay",
            json=overlay.model_dump(mode="json"),
        )

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


async def test_update_talking_head_trim_persists_trim_and_focal_point(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    video = tmp_path / "presenter.mp4"
    _make_video(ffmpeg_dir, video, audio=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Trim"})).json()
        campaign_id = created["id"]
        await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(video)},
        )
        response = await client.put(
            f"/campaigns/{campaign_id}/talking-head/trim",
            json={
                "trim_start_ms": 200,
                "trim_end_ms": 1800,
                "focal_x": 0.25,
                "focal_y": 0.75,
            },
        )
        body = response.json()
        refetched = (await client.get(f"/campaigns/{campaign_id}")).json()

    assert response.status_code == 200
    talking_head = body["talking_head"]
    assert talking_head["trim_start_ms"] == 200
    assert talking_head["trim_end_ms"] == 1800
    assert talking_head["focal_x"] == pytest.approx(0.25)
    assert talking_head["focal_y"] == pytest.approx(0.75)
    assert refetched["talking_head"]["trim_start_ms"] == 200
    assert refetched["talking_head"]["trim_end_ms"] == 1800
    assert refetched["talking_head"]["focal_x"] == pytest.approx(0.25)
    assert refetched["talking_head"]["focal_y"] == pytest.approx(0.75)


async def test_update_talking_head_trim_clamps_server_side(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    video = tmp_path / "presenter.mp4"
    _make_video(ffmpeg_dir, video, audio=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Clamp"})).json()
        campaign_id = created["id"]
        await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(video)},
        )

        negative_start_response = await client.put(
            f"/campaigns/{campaign_id}/talking-head/trim",
            json={
                "trim_start_ms": -500,
                "trim_end_ms": 1000,
                "focal_x": 0.5,
                "focal_y": 0.5,
            },
        )

        huge_end = (
            await client.put(
                f"/campaigns/{campaign_id}/talking-head/trim",
                json={
                    "trim_start_ms": 0,
                    "trim_end_ms": 999_999,
                    "focal_x": 0.5,
                    "focal_y": 0.5,
                },
            )
        ).json()["talking_head"]

        inverted = (
            await client.put(
                f"/campaigns/{campaign_id}/talking-head/trim",
                json={
                    "trim_start_ms": 1800,
                    "trim_end_ms": 200,
                    "focal_x": 0.5,
                    "focal_y": 0.5,
                },
            )
        ).json()["talking_head"]

    assert negative_start_response.status_code == 422

    assert huge_end["trim_start_ms"] == 0
    assert huge_end["trim_end_ms"] <= 2000

    assert inverted["trim_start_ms"] < inverted["trim_end_ms"]
    assert inverted["trim_end_ms"] - inverted["trim_start_ms"] >= 1


async def test_update_talking_head_trim_invalidates_alpha_cache(
    app_with_database: FastAPI,
    ffmpeg_dir: Path,
    tmp_path: Path,
) -> None:
    video = tmp_path / "presenter.mp4"
    _make_video(ffmpeg_dir, video, audio=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Cache"})).json()
        campaign_id = created["id"]
        await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(video)},
        )

    database = app_with_database.state.database
    with database.session_factory() as session:
        campaign = session.get(Campaign, campaign_id)
        assert campaign is not None
        campaign.alpha_cache_key = "deadbeef"
        campaign.alpha_cache_path = "cache/deadbeef.mov"
        session.commit()

    async with await client_for(app_with_database) as client:
        response = await client.put(
            f"/campaigns/{campaign_id}/talking-head/trim",
            json={
                "trim_start_ms": 100,
                "trim_end_ms": 1900,
                "focal_x": 0.5,
                "focal_y": 0.5,
            },
        )

    assert response.status_code == 200

    with database.session_factory() as session:
        campaign = session.get(Campaign, campaign_id)
        assert campaign is not None
        assert campaign.alpha_cache_key is None
        assert campaign.alpha_cache_path is None


async def test_update_talking_head_trim_422s_when_no_talking_head_exists(
    app_with_database: FastAPI,
) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "No head"})).json()
        response = await client.put(
            f"/campaigns/{created['id']}/talking-head/trim",
            json={
                "trim_start_ms": 0,
                "trim_end_ms": 1000,
                "focal_x": 0.5,
                "focal_y": 0.5,
            },
        )

    assert response.status_code == 422


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


def _seed_staged_recording(
    session: Session,
    tmp_workspace: WorkspaceLayout,
    campaign_id: str,
    *,
    company_name: str,
    sort_order: int = 0,
    source_path: str | None = None,
    output_bytes: bytes = b"staged-output",
    last_rendered_at: str = "2026-01-01T00:00:00Z",
) -> tuple[MediaAsset, RenderJob, Path]:
    output_dir = tmp_workspace.outputs / campaign_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{company_name}.mp4"
    output_file.write_bytes(output_bytes)

    resolved_source = source_path or f"C:/videos/{company_name.lower().replace(' ', '_')}.mp4"

    asset = MediaAsset(
        campaign_id=campaign_id,
        role=AssetRole.SCREEN_RECORDING.value,
        source_path=resolved_source,
        source_filename=Path(resolved_source).name,
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
        last_rendered_at=last_rendered_at,
    )
    session.add(asset)
    session.flush()

    job = RenderJob(
        campaign_id=campaign_id,
        asset_id=asset.id,
        job_type=JobType.VIDEO_RENDER.value,
        status=JobStatus.COMPLETED.value,
        queue_position=sort_order + 1,
        output_path=output_file.relative_to(tmp_workspace.root).as_posix(),
        output_filename=output_file.name,
        finished_at=last_rendered_at,
    )
    session.add(job)
    session.commit()
    session.refresh(asset)
    session.refresh(job)
    return asset, job, output_file


async def test_update_recording_renames_staged_output_on_disk(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Rename output"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        recording, job, output_file = _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Beta Inc",
        )
        recording_id = recording.id
        job_id = job.id

    async with await client_for(app_with_database) as client:
        body = (
            await client.patch(
                f"/campaigns/{campaign_id}/recordings/{recording_id}",
                json={"company_name": "Gamma LLC"},
            )
        ).json()

    assert body["company_name"] == "Gamma LLC"
    assert body["output_basename"] == "Gamma LLC"
    assert not output_file.is_file()
    renamed = tmp_workspace.outputs / campaign_id / "Gamma LLC.mp4"
    assert renamed.is_file()
    assert renamed.read_bytes() == b"staged-output"

    with database.session_factory() as session:
        refreshed_job = session.get(RenderJob, job_id)
        refreshed_recording = session.get(MediaAsset, recording_id)
        assert refreshed_job is not None
        assert refreshed_job.output_path == f"outputs/{campaign_id}/Gamma LLC.mp4"
        assert refreshed_job.output_filename == "Gamma LLC.mp4"
        assert refreshed_recording is not None
        assert refreshed_recording.last_rendered_at == "2026-01-01T00:00:00Z"


async def test_update_recording_reports_error_when_disk_rename_fails(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Rename fail"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        recording, job, output_file = _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Beta Inc",
        )
        recording_id = recording.id
        job_id = job.id

    def fail_rename(_self: Path, _target: Path) -> None:
        raise OSError("access denied")

    monkeypatch.setattr(Path, "rename", fail_rename)

    async with await client_for(app_with_database) as client:
        response = await client.patch(
            f"/campaigns/{campaign_id}/recordings/{recording_id}",
            json={"company_name": "Gamma LLC"},
        )

    assert response.status_code == 500
    assert output_file.is_file()

    with database.session_factory() as session:
        refreshed_job = session.get(RenderJob, job_id)
        refreshed_recording = session.get(MediaAsset, recording_id)
        assert refreshed_job is not None
        assert refreshed_job.output_filename == "Beta Inc.mp4"
        assert refreshed_recording is not None
        assert refreshed_recording.company_name == "Beta Inc"
        assert refreshed_recording.last_rendered_at == "2026-01-01T00:00:00Z"


async def test_update_recording_rolls_back_disk_rename_when_commit_fails(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Commit fail"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        recording, job, output_file = _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Beta Inc",
        )
        recording_id = recording.id
        job_id = job.id

    def fail_commit(self: Session) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr("sqlalchemy.orm.Session.commit", fail_commit)

    transport = ASGITransport(app=app_with_database, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1/api/v1",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as client:
        response = await client.patch(
            f"/campaigns/{campaign_id}/recordings/{recording_id}",
            json={"company_name": "Gamma LLC"},
        )

    assert response.status_code == 500
    assert output_file.is_file()
    assert not (output_file.parent / "Gamma LLC.mp4").exists()

    with database.session_factory() as session:
        refreshed_job = session.get(RenderJob, job_id)
        refreshed_recording = session.get(MediaAsset, recording_id)
        assert refreshed_job is not None
        assert refreshed_job.output_filename == "Beta Inc.mp4"
        assert refreshed_recording is not None
        assert refreshed_recording.company_name == "Beta Inc"


async def test_update_recording_rename_resolves_staged_output_collision(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Collision"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Acme Corp",
            sort_order=0,
            output_bytes=b"acme",
        )
        recording, _, beta_file = _seed_staged_recording(
            session,
            tmp_workspace,
            campaign_id,
            company_name="Beta Inc",
            sort_order=1,
            output_bytes=b"beta",
        )
        recording_id = recording.id

    async with await client_for(app_with_database) as client:
        body = (
            await client.patch(
                f"/campaigns/{campaign_id}/recordings/{recording_id}",
                json={"company_name": "Acme Corp"},
            )
        ).json()

    assert body["company_name"] == "Acme Corp (2)"
    assert body["output_basename"] == "Acme Corp (2)"
    assert (tmp_workspace.outputs / campaign_id / "Acme Corp.mp4").read_bytes() == b"acme"
    assert not beta_file.is_file()
    assert (tmp_workspace.outputs / campaign_id / "Acme Corp (2).mp4").read_bytes() == b"beta"


async def test_update_recording_without_staged_output_updates_basename_only(
    app_with_database: FastAPI,
    tmp_workspace: WorkspaceLayout,
) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "No output"})).json()
        campaign_id = created["id"]

    database = app_with_database.state.database
    with database.session_factory() as session:
        asset = MediaAsset(
            campaign_id=campaign_id,
            role=AssetRole.SCREEN_RECORDING.value,
            source_path="C:/videos/unrendered.mp4",
            source_filename="unrendered.mp4",
            company_name="Old Name",
            output_basename="Old Name",
            sort_order=0,
            probe_status=ProbeStatus.OK.value,
            duration_ms=2000,
            width=640,
            height=480,
            fps=30.0,
            video_codec="h264",
            has_audio=0,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        recording_id = asset.id

    output_dir = tmp_workspace.outputs / campaign_id
    assert not output_dir.exists()

    async with await client_for(app_with_database) as client:
        body = (
            await client.patch(
                f"/campaigns/{campaign_id}/recordings/{recording_id}",
                json={"company_name": "Future Name"},
            )
        ).json()

    assert body["company_name"] == "Future Name"
    assert body["output_basename"] == "Future Name"
    assert not output_dir.exists()


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


# --- Ticket 14: preset library ----------------------------------------------


async def test_create_preset_then_list_and_apply(app_with_database: FastAPI) -> None:
    overlay = OverlayConfig(anchor="top_left", size=SizeConfig(width=300, height=300))

    async with await client_for(app_with_database) as client:
        campaign = (await client.post("/campaigns", json={})).json()
        created = await client.post(
            "/overlay-presets",
            json={"name": "Corner", "overlay": overlay.model_dump(mode="json")},
        )
        listed = (await client.get("/overlay-presets")).json()
        applied = await client.post(
            f"/campaigns/{campaign['id']}/apply-preset",
            json={"preset_id": created.json()["id"]},
        )

    assert created.status_code == 201
    assert created.json()["name"] == "Corner"
    assert listed["presets"][0]["name"] == "Corner"

    assert applied.status_code == 200
    applied_overlay = OverlayConfig.model_validate_json(applied.json()["overlay_config"])
    assert applied_overlay.anchor == "top_left"


async def test_create_preset_rejects_a_duplicate_name(app_with_database: FastAPI) -> None:
    overlay = OverlayConfig().model_dump(mode="json")

    async with await client_for(app_with_database) as client:
        await client.post("/overlay-presets", json={"name": "Dup", "overlay": overlay})
        response = await client.post("/overlay-presets", json={"name": "Dup", "overlay": overlay})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_rename_and_delete_preset(app_with_database: FastAPI) -> None:
    overlay = OverlayConfig().model_dump(mode="json")

    async with await client_for(app_with_database) as client:
        created = (
            await client.post("/overlay-presets", json={"name": "Old name", "overlay": overlay})
        ).json()
        renamed = await client.patch(f"/overlay-presets/{created['id']}", json={"name": "New name"})
        deleted = await client.delete(f"/overlay-presets/{created['id']}")
        listed = (await client.get("/overlay-presets")).json()

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "New name"
    assert deleted.status_code == 204
    assert listed["presets"] == []


# --- editor locking (ticket 21) -------------------------------------------


def _add_active_job(database: Database, campaign_id: str, *, status: str = "waiting") -> None:
    with database.session_factory() as session:
        session.add(
            RenderJob(
                campaign_id=campaign_id,
                job_type="video_render",
                status=status,
                queue_position=1,
            )
        )
        session.commit()


async def test_campaign_with_no_jobs_is_unlocked(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Unlocked"})).json()

    assert created["is_locked"] is False
    assert created["lock_reason"] is None


async def test_campaign_with_a_queued_job_reports_locked(app_with_database: FastAPI) -> None:
    database = app_with_database.state.database
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Locked"})).json()
        _add_active_job(database, created["id"])
        body = (await client.get(f"/campaigns/{created['id']}")).json()

    assert body["is_locked"] is True
    assert body["lock_reason"] == (
        "Editing is locked while this campaign has queued or active render jobs."
    )


@pytest.mark.parametrize("status", ["waiting", "preparing", "rendering", "encoding"])
async def test_every_active_status_locks_the_campaign(
    app_with_database: FastAPI, status: str
) -> None:
    database = app_with_database.state.database
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Locked"})).json()
        _add_active_job(database, created["id"], status=status)
        body = (await client.get(f"/campaigns/{created['id']}")).json()

    assert body["is_locked"] is True


@pytest.mark.parametrize("status", ["completed", "failed"])
async def test_terminal_job_statuses_do_not_lock_the_campaign(
    app_with_database: FastAPI, status: str
) -> None:
    database = app_with_database.state.database
    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Not locked"})).json()
        _add_active_job(database, created["id"], status=status)
        body = (await client.get(f"/campaigns/{created['id']}")).json()

    assert body["is_locked"] is False


async def test_locked_campaign_rejects_overlay_updates(app_with_database: FastAPI) -> None:
    database = app_with_database.state.database
    overlay = OverlayConfig().model_dump(mode="json")

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Locked"})).json()
        _add_active_job(database, created["id"])
        response = await client.put(f"/campaigns/{created['id']}/overlay", json=overlay)

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "conflict"
    assert body["error"]["message"] == (
        "Editing is locked while this campaign has queued or active render jobs."
    )


async def test_locked_campaign_rejects_quality_updates(app_with_database: FastAPI) -> None:
    database = app_with_database.state.database

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Locked quality"})).json()
        _add_active_job(database, created["id"])
        response = await client.patch(
            f"/campaigns/{created['id']}/quality",
            json={"quality_override": "high"},
        )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "conflict"
    assert body["error"]["message"] == (
        "Editing is locked while this campaign has queued or active render jobs."
    )


async def test_locked_campaign_rejects_talking_head_trim_updates(
    app_with_database: FastAPI, ffmpeg_dir: Path, tmp_path: Path
) -> None:
    database = app_with_database.state.database
    video = tmp_path / "presenter.mp4"
    _make_video(ffmpeg_dir, video, audio=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Locked"})).json()
        campaign_id = created["id"]
        await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(video)},
        )
        _add_active_job(database, campaign_id)
        response = await client.put(
            f"/campaigns/{campaign_id}/talking-head/trim",
            json={"trim_start_ms": 0, "trim_end_ms": 500, "focal_x": 0.5, "focal_y": 0.5},
        )

    assert response.status_code == 409


async def test_locked_campaign_rejects_assign_talking_head(
    app_with_database: FastAPI, ffmpeg_dir: Path, tmp_path: Path
) -> None:
    """Finding E2: swapping the talking head mid-queue changes the render as
    surely as a trim does, so it must be lock-guarded the same way."""
    database = app_with_database.state.database
    first = tmp_path / "presenter.mp4"
    _make_video(ffmpeg_dir, first, audio=True)
    second = tmp_path / "replacement.mp4"
    _make_video(ffmpeg_dir, second, audio=True)

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Locked"})).json()
        campaign_id = created["id"]
        await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(first)},
        )
        _add_active_job(database, campaign_id)
        response = await client.put(
            f"/campaigns/{campaign_id}/talking-head",
            json={"source_path": str(second)},
        )

    assert response.status_code == 409


async def test_locked_campaign_rejects_apply_preset(app_with_database: FastAPI) -> None:
    database = app_with_database.state.database
    overlay = OverlayConfig().model_dump(mode="json")

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Locked"})).json()
        preset = (
            await client.post("/overlay-presets", json={"name": "P", "overlay": overlay})
        ).json()
        _add_active_job(database, created["id"])
        response = await client.post(
            f"/campaigns/{created['id']}/apply-preset",
            json={"preset_id": preset["id"]},
        )

    assert response.status_code == 409


async def test_a_campaigns_lock_does_not_affect_another_campaign(
    app_with_database: FastAPI,
) -> None:
    database = app_with_database.state.database
    overlay = OverlayConfig().model_dump(mode="json")

    async with await client_for(app_with_database) as client:
        locked = (await client.post("/campaigns", json={"name": "Locked"})).json()
        other = (await client.post("/campaigns", json={"name": "Other"})).json()
        _add_active_job(database, locked["id"])

        other_body = (await client.get(f"/campaigns/{other['id']}")).json()
        response = await client.put(f"/campaigns/{other['id']}/overlay", json=overlay)

    assert other_body["is_locked"] is False
    assert response.status_code == 200


async def test_cancel_queue_clears_jobs_and_unlocks_editing(app_with_database: FastAPI) -> None:
    database = app_with_database.state.database

    async with await client_for(app_with_database) as client:
        created = (await client.post("/campaigns", json={"name": "Locked"})).json()
        _add_active_job(database, created["id"])
        before = (await client.get(f"/campaigns/{created['id']}")).json()
        response = await client.post(f"/campaigns/{created['id']}/cancel-queue")

    assert before["is_locked"] is True
    assert response.status_code == 200
    body = response.json()
    assert body["is_locked"] is False
    assert body["lock_reason"] is None

    with database.session_factory() as session:
        remaining = session.scalars(
            select(RenderJob).where(RenderJob.campaign_id == created["id"])
        ).all()
        assert remaining == []


async def test_cancel_queue_only_clears_active_jobs_for_that_campaign(
    app_with_database: FastAPI,
) -> None:
    database = app_with_database.state.database

    async with await client_for(app_with_database) as client:
        target = (await client.post("/campaigns", json={"name": "Target"})).json()
        other = (await client.post("/campaigns", json={"name": "Other"})).json()
        _add_active_job(database, target["id"])
        _add_active_job(database, other["id"])
        await client.post(f"/campaigns/{target['id']}/cancel-queue")
        other_body = (await client.get(f"/campaigns/{other['id']}")).json()

    assert other_body["is_locked"] is True


async def test_cancel_queue_404s_for_an_unknown_id(app_with_database: FastAPI) -> None:
    async with await client_for(app_with_database) as client:
        response = await client.post("/campaigns/does-not-exist/cancel-queue")

    assert response.status_code == 404
