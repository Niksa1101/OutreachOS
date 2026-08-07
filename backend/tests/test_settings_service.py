"""Settings service helpers — quality inheritance and cache management."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.models import AppSettings
from outreachos_backend.core.settings_service import (
    GLOBAL_QUEUE_LOCK_REASON,
    clear_workspace_cache,
    detected_encoder_default,
    queue_has_activity,
    resolve_encoder_override,
    resolve_quality,
    update_app_settings,
)
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.models import Campaign, RenderJob


@pytest.fixture
def session(tmp_workspace: WorkspaceLayout) -> Iterator[Session]:
    database = Database(tmp_workspace.database)
    outcome = migrate.run_migrations(database.engine, database.path)
    assert outcome.ok, outcome.detail
    migrate.heal_app_settings(database.engine)
    db_session = database.session_factory()
    yield db_session
    db_session.close()
    database.dispose()


def test_resolve_quality_inherits_global_preset(session: Session) -> None:
    settings = session.query(AppSettings).filter(AppSettings.id == 1).one()
    settings.quality_preset = "high"
    session.commit()

    assert resolve_quality(session, quality_override=None) == "high"


def test_resolve_quality_honors_campaign_override(session: Session) -> None:
    settings = session.query(AppSettings).filter(AppSettings.id == 1).one()
    settings.quality_preset = "high"
    session.commit()

    assert resolve_quality(session, quality_override="draft") == "draft"


def test_detected_encoder_default_picks_first_available() -> None:
    assert detected_encoder_default(json.dumps(["libx264"])) == "libx264"
    assert detected_encoder_default(json.dumps(["h264_nvenc", "libx264"])) == "h264_nvenc"


def test_clear_workspace_cache_resets_campaign_pointers(
    session: Session,
    tmp_workspace: WorkspaceLayout,
) -> None:
    cache_file = tmp_workspace.cache / "alpha" / "key.mov"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(b"cached")

    campaign = Campaign(
        name="Test",
        overlay_config='{"schema_version":1}',
        overlay_schema_version=1,
        alpha_cache_key="key",
        alpha_cache_path="cache/alpha/key.mov",
    )
    session.add(campaign)
    session.commit()

    freed = clear_workspace_cache(session, tmp_workspace)

    assert freed >= len(b"cached")
    assert not cache_file.exists()
    session.refresh(campaign)
    assert campaign.alpha_cache_key is None
    assert campaign.alpha_cache_path is None


def test_update_app_settings_validates_encoder(session: Session) -> None:
    with pytest.raises(Exception) as exc:
        update_app_settings(
            session,
            encoder_override="not_real",
            fields_set={"encoder_override"},
        )
    assert "Unknown encoder" in str(exc.value)


def test_resolve_encoder_override(session: Session) -> None:
    settings = session.query(AppSettings).filter(AppSettings.id == 1).one()
    settings.encoder_override = "h264_qsv"
    session.commit()
    assert resolve_encoder_override(session) == "h264_qsv"


def test_queue_has_activity(session: Session) -> None:
    assert queue_has_activity(session) is False

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

    assert queue_has_activity(session) is True


def test_clear_workspace_cache_rejects_while_queue_busy(
    session: Session,
    tmp_workspace: WorkspaceLayout,
) -> None:
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

    with pytest.raises(Exception) as exc:
        clear_workspace_cache(session, tmp_workspace)
    assert GLOBAL_QUEUE_LOCK_REASON in str(exc.value)
