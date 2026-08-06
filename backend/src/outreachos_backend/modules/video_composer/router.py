"""Video Composer routes — campaign CRUD."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from outreachos_backend.core.db import get_session
from outreachos_backend.modules.video_composer import service
from outreachos_backend.modules.video_composer.deps import BinariesDep, WorkspaceDep
from outreachos_backend.modules.video_composer.schemas import (
    AssetRelocateRequest,
    CampaignCreateRequest,
    CampaignDeletePreview,
    CampaignDetail,
    CampaignListResponse,
    CampaignUpdateRequest,
    PreviewFrameResponse,
    RecordingDetail,
    RecordingImportRequest,
    RecordingImportResponse,
    RecordingUpdateRequest,
    TalkingHeadAssignRequest,
)

router = APIRouter(tags=["video-composer"])
router.redirect_slashes = False


@router.get("/campaigns", summary="List campaigns")
def list_campaigns(
    session: Annotated[Session, Depends(get_session)],
) -> CampaignListResponse:
    return CampaignListResponse(campaigns=service.list_campaigns(session))


@router.post(
    "/campaigns",
    status_code=status.HTTP_201_CREATED,
    summary="Create a campaign",
)
def create_campaign(
    body: CampaignCreateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> CampaignDetail:
    return service.create_campaign(session, name=body.name)


@router.get("/campaigns/{campaign_id}", summary="Read one campaign")
def get_campaign(
    campaign_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> CampaignDetail:
    return service.get_campaign(session, campaign_id)


@router.post(
    "/campaigns/{campaign_id}/duplicate",
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate a campaign",
)
def duplicate_campaign(
    campaign_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> CampaignDetail:
    return service.duplicate_campaign(session, campaign_id)


@router.patch("/campaigns/{campaign_id}", summary="Rename a campaign")
def rename_campaign(
    campaign_id: str,
    body: CampaignUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> CampaignDetail:
    return service.rename_campaign(session, campaign_id, body.name)


@router.put(
    "/campaigns/{campaign_id}/talking-head",
    summary="Assign or replace the campaign talking head",
)
def assign_talking_head(
    campaign_id: str,
    body: TalkingHeadAssignRequest,
    session: Annotated[Session, Depends(get_session)],
    binaries: BinariesDep,
    workspace: WorkspaceDep,
) -> CampaignDetail:
    return service.assign_talking_head(
        session,
        binaries,
        workspace,
        campaign_id,
        source_path=body.source_path,
    )


@router.post(
    "/campaigns/{campaign_id}/recordings/import",
    summary="Import screen recordings in batch",
)
def import_recordings(
    campaign_id: str,
    body: RecordingImportRequest,
    session: Annotated[Session, Depends(get_session)],
    binaries: BinariesDep,
) -> RecordingImportResponse:
    return service.import_recordings(
        session,
        binaries,
        campaign_id,
        source_paths=body.source_paths,
    )


@router.patch(
    "/campaigns/{campaign_id}/recordings/{recording_id}",
    summary="Rename a screen recording's company name",
)
def update_recording(
    campaign_id: str,
    recording_id: str,
    body: RecordingUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> RecordingDetail:
    return service.update_recording(
        session,
        campaign_id,
        recording_id,
        company_name=body.company_name,
    )


@router.delete(
    "/campaigns/{campaign_id}/recordings/{recording_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a screen recording reference",
)
def delete_recording(
    campaign_id: str,
    recording_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    service.delete_recording(session, campaign_id, recording_id)


@router.put(
    "/campaigns/{campaign_id}/assets/{asset_id}/relocate",
    summary="Relocate a missing source file to a new path",
)
def relocate_asset(
    campaign_id: str,
    asset_id: str,
    body: AssetRelocateRequest,
    session: Annotated[Session, Depends(get_session)],
    binaries: BinariesDep,
    workspace: WorkspaceDep,
) -> CampaignDetail:
    return service.relocate_asset(
        session,
        binaries,
        workspace,
        campaign_id,
        asset_id,
        source_path=body.source_path,
    )


@router.get(
    "/campaigns/{campaign_id}/preview-frame",
    summary="Get the split-view preview's background frame",
)
def get_preview_frame(
    campaign_id: str,
    session: Annotated[Session, Depends(get_session)],
    binaries: BinariesDep,
    workspace: WorkspaceDep,
) -> PreviewFrameResponse:
    return service.get_preview_frame(session, binaries, workspace, campaign_id)


@router.get(
    "/campaigns/{campaign_id}/delete-preview",
    summary="Preview what deleting a campaign removes",
)
def preview_delete_campaign(
    campaign_id: str,
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
) -> CampaignDeletePreview:
    return service.get_delete_preview(session, workspace, campaign_id)


@router.delete(
    "/campaigns/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a campaign",
)
def delete_campaign(
    campaign_id: str,
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
) -> None:
    service.delete_campaign(session, workspace, campaign_id)
