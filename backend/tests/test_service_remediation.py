"""P2 remediation — service-level tests that do not require ffmpeg."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.enums import AssetRole, ProbeStatus
from outreachos_backend.core.events import EventBus
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.models import Campaign, MediaAsset
from outreachos_backend.modules.video_composer.service import (
    _existing_campaign_paths,
    _preview_frame_timestamp_ms,
    _probe_source_video_soft,
    cancel_queue,
    get_preview_frame,
    import_recordings,
    update_recording,
)
from outreachos_backend.modules.video_composer.validation import (
    ValidationIssueCode,
    validate_campaign,
)
from outreachos_backend.rendering.binaries import Binaries


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
        overlay_config='{"schema_version":1}',
        overlay_schema_version=1,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def test_existing_campaign_paths_includes_talking_head(
    session: Session, campaign: Campaign
) -> None:
    head_path = "C:/videos/presenter.mp4"
    session.add(
        MediaAsset(
            campaign_id=campaign.id,
            role=AssetRole.TALKING_HEAD.value,
            source_path=head_path,
            source_filename="presenter.mp4",
            probe_status=ProbeStatus.OK.value,
            duration_ms=1000,
            width=640,
            height=360,
            fps=30.0,
            video_codec="h264",
            has_audio=1,
            trim_start_ms=0,
            trim_end_ms=1000,
            focal_x=0.5,
            focal_y=0.5,
        )
    )
    session.commit()

    paths = _existing_campaign_paths(session, campaign.id)
    assert paths == {head_path}


def test_update_recording_sets_and_clears_name_auto_suffixed(
    session: Session, campaign: Campaign
) -> None:
    session.add(
        MediaAsset(
            campaign_id=campaign.id,
            role=AssetRole.SCREEN_RECORDING.value,
            source_path="C:/videos/acme.mp4",
            source_filename="acme.mp4",
            company_name="Acme Corp",
            output_basename="Acme Corp",
            sort_order=0,
            probe_status=ProbeStatus.OK.value,
            duration_ms=5000,
            width=640,
            height=360,
            fps=30.0,
            video_codec="h264",
            has_audio=0,
        )
    )
    recording = MediaAsset(
        campaign_id=campaign.id,
        role=AssetRole.SCREEN_RECORDING.value,
        source_path="C:/videos/other.mp4",
        source_filename="other.mp4",
        company_name="Other Inc",
        output_basename="Other Inc",
        sort_order=1,
        probe_status=ProbeStatus.OK.value,
        duration_ms=5000,
        width=640,
        height=360,
        fps=30.0,
        video_codec="h264",
        has_audio=0,
    )
    session.add(recording)
    session.commit()
    session.refresh(recording)

    updated = update_recording(
        session,
        campaign.id,
        recording.id,
        company_name="Acme Corp",
    )
    assert updated.company_name == "Acme Corp (2)"
    row = session.get(MediaAsset, recording.id)
    assert row is not None
    assert row.name_auto_suffixed == 1

    cleared = update_recording(
        session,
        campaign.id,
        recording.id,
        company_name="Unique Name",
    )
    assert cleared.company_name == "Unique Name"
    row = session.get(MediaAsset, recording.id)
    assert row is not None
    assert row.name_auto_suffixed == 0


def test_duplicate_warning_emitted_from_persisted_flag_only() -> None:
    recording = MediaAsset(
        id="rec-flagged",
        campaign_id="camp-1",
        role=AssetRole.SCREEN_RECORDING.value,
        source_path="C:/videos/unrelated_xyz.mp4",
        source_filename="unrelated_xyz.mp4",
        company_name="Acme Corp (2)",
        output_basename="Acme Corp (2)",
        sort_order=1,
        probe_status=ProbeStatus.OK.value,
        duration_ms=8000,
        width=640,
        height=360,
        fps=30.0,
        video_codec="h264",
        has_audio=0,
        name_auto_suffixed=1,
    )

    result = validate_campaign(
        talking_head=MediaAsset(
            id="head-1",
            campaign_id="camp-1",
            role=AssetRole.TALKING_HEAD.value,
            source_path="C:/videos/head.mp4",
            source_filename="head.mp4",
            probe_status=ProbeStatus.OK.value,
            duration_ms=5000,
            width=640,
            height=360,
            fps=30.0,
            video_codec="h264",
            has_audio=1,
            file_missing=0,
            trim_start_ms=0,
            trim_end_ms=5000,
            focal_x=0.5,
            focal_y=0.5,
        ),
        recordings=[
            MediaAsset(
                id="rec-1",
                campaign_id="camp-1",
                role=AssetRole.SCREEN_RECORDING.value,
                source_path="C:/videos/acme.mp4",
                source_filename="acme.mp4",
                company_name="Acme Corp",
                output_basename="Acme Corp",
                sort_order=0,
                probe_status=ProbeStatus.OK.value,
                duration_ms=8000,
                width=640,
                height=360,
                fps=30.0,
                video_codec="h264",
                has_audio=0,
            ),
            recording,
        ],
    )

    warnings = [
        issue for issue in result.issues if issue.code == ValidationIssueCode.DUPLICATE_COMPANY_NAME
    ]
    assert len(warnings) == 1
    assert warnings[0].asset_id == "rec-flagged"


def test_probe_source_video_soft_missing_path() -> None:
    outcome = _probe_source_video_soft(MagicMock(spec=Binaries), Path("C:/missing/file.mp4"))
    assert outcome.missing is True
    assert outcome.error == "That file could not be found."


def test_import_recordings_marks_missing_file(
    session: Session, campaign: Campaign, tmp_path: Path
) -> None:
    missing = tmp_path / "gone.mp4"
    missing_str = str(missing.resolve())

    result = import_recordings(
        session,
        MagicMock(spec=Binaries),
        campaign.id,
        source_paths=[missing_str],
    )

    assert result.recording_count == 1
    assert len(result.failed) == 1
    assert result.added[0].file_missing is True


def test_preview_frame_timestamp_defaults_to_two_seconds() -> None:
    assert _preview_frame_timestamp_ms(10_000) == 2000
    assert _preview_frame_timestamp_ms(4_000) == 2000


def test_preview_frame_timestamp_clamps_to_midpoint_for_short_clips() -> None:
    assert _preview_frame_timestamp_ms(3_000) == 1500
    assert _preview_frame_timestamp_ms(1_000) == 500
    assert _preview_frame_timestamp_ms(0) == 0


def test_preview_frame_with_no_recordings_is_unavailable_without_error(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    response = get_preview_frame(session, MagicMock(spec=Binaries), tmp_workspace, campaign.id)
    assert response.available is False
    assert response.frame_path is None
    assert response.error is None


def test_preview_frame_reports_missing_first_recording_file(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout, tmp_path: Path
) -> None:
    missing = tmp_path / "gone.mp4"
    session.add(
        MediaAsset(
            campaign_id=campaign.id,
            role=AssetRole.SCREEN_RECORDING.value,
            source_path=str(missing.resolve()),
            source_filename="gone.mp4",
            company_name="Acme Corp",
            output_basename="Acme Corp",
            sort_order=0,
            probe_status=ProbeStatus.OK.value,
            duration_ms=5000,
            file_missing=1,
        )
    )
    session.commit()

    response = get_preview_frame(session, MagicMock(spec=Binaries), tmp_workspace, campaign.id)
    assert response.available is False
    assert response.frame_path is None
    assert response.error == "The first recording's file could not be found."


def test_cancel_queue_publishes_lock_changed_event(
    session: Session, campaign: Campaign, tmp_workspace: WorkspaceLayout
) -> None:
    """Finding E6: nothing previously asserted that clearing the queue tells
    subscribers the editor unlocked."""
    event_bus = MagicMock(spec=EventBus)

    cancel_queue(session, event_bus, tmp_workspace, campaign.id)

    event_bus.campaign_lock_changed.assert_called_once_with(campaign.id, locked=False)
