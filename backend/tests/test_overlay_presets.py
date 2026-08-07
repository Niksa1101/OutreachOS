"""Ticket 14 — preset library service tests."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.errors import ApiError
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.models import Campaign, OverlayPreset
from outreachos_backend.modules.video_composer.service import (
    apply_preset_to_campaign,
    create_preset,
    delete_preset,
    get_campaign,
    rename_preset,
)
from outreachos_backend.rendering.config import OverlayConfig


@pytest.fixture
def session(tmp_workspace: WorkspaceLayout) -> Generator[Session, None, None]:
    database = Database(tmp_workspace.database)
    outcome = migrate.run_migrations(database.engine, database.path)
    assert outcome.ok, outcome.detail
    migrate.heal_app_settings(database.engine)
    db_session = database.session_factory()
    try:
        yield db_session
    finally:
        db_session.close()
        database.dispose()


@pytest.fixture
def campaign(session: Session) -> Campaign:
    campaign = Campaign(
        name="Test campaign",
        overlay_config=OverlayConfig().model_dump_json(),
        overlay_schema_version=1,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def test_save_as_preset_captures_the_full_overlay_config(session: Session) -> None:
    overlay = OverlayConfig(anchor="top_left", opacity=0.5)
    detail = create_preset(session, name="Bold circle", overlay=overlay)

    assert detail.name == "Bold circle"
    assert detail.overlay_schema_version == 1
    saved = OverlayConfig.model_validate_json(detail.overlay_config)
    assert saved.anchor == "top_left"
    assert saved.opacity == 0.5


def test_preset_names_must_be_unique(session: Session) -> None:
    create_preset(session, name="My preset", overlay=OverlayConfig())

    with pytest.raises(ApiError) as exc_info:
        create_preset(session, name="My preset", overlay=OverlayConfig())

    assert exc_info.value.status_code == 409


def test_apply_preset_copies_values_into_the_campaign(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    preset = create_preset(session, name="Wide banner", overlay=OverlayConfig(anchor="top_right"))

    detail = apply_preset_to_campaign(session, tmp_workspace, campaign.id, preset.id)

    applied = OverlayConfig.model_validate_json(detail.overlay_config)
    assert applied.anchor == "top_right"


def test_editing_a_preset_does_not_change_a_campaign_that_already_applied_it(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    preset = create_preset(session, name="Original", overlay=OverlayConfig(anchor="top_right"))
    apply_preset_to_campaign(session, tmp_workspace, campaign.id, preset.id)

    rename_preset(session, preset.id, "Renamed")

    detail = get_campaign(session, campaign.id)
    applied = OverlayConfig.model_validate_json(detail.overlay_config)
    assert applied.anchor == "top_right"


def test_deleting_a_preset_does_not_change_a_campaign_that_already_applied_it(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    preset = create_preset(session, name="Doomed", overlay=OverlayConfig(anchor="top_right"))
    apply_preset_to_campaign(session, tmp_workspace, campaign.id, preset.id)

    delete_preset(session, preset.id)

    detail = get_campaign(session, campaign.id)
    applied = OverlayConfig.model_validate_json(detail.overlay_config)
    assert applied.anchor == "top_right"


def test_apply_preset_upgrades_an_older_schema_version(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    preset = OverlayPreset(
        name="Legacy",
        overlay_config='{"schema_version": 1, "anchor": "top_left"}',
        overlay_schema_version=1,
    )
    session.add(preset)
    session.commit()
    session.refresh(preset)

    detail = apply_preset_to_campaign(session, tmp_workspace, campaign.id, preset.id)

    applied = OverlayConfig.model_validate_json(detail.overlay_config)
    assert applied.schema_version == 1
    assert applied.anchor == "top_left"
