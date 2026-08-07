"""Video Composer routes — campaign CRUD."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from outreachos_backend.core.db import get_session
from outreachos_backend.modules.video_composer import service
from outreachos_backend.modules.video_composer.deps import (
    BinariesDep,
    EventBusDep,
    WorkerPoolDep,
    WorkspaceDep,
)
from outreachos_backend.modules.video_composer.schemas import (
    ApplyPresetRequest,
    AssetRelocateRequest,
    CampaignCreateRequest,
    CampaignDeletePreview,
    CampaignDetail,
    CampaignListResponse,
    CampaignOutputsResponse,
    CampaignQualityUpdateRequest,
    CampaignUpdateRequest,
    ExportAllRequest,
    ExportAllResponse,
    GeneratePlanResponse,
    GenerateVideosRequest,
    GenerateVideosResponse,
    OverlayPresetCreateRequest,
    OverlayPresetDetail,
    OverlayPresetListResponse,
    OverlayPresetRenameRequest,
    OverlayPresetSummary,
    PreviewFrameResponse,
    RecordingDetail,
    RecordingImportRequest,
    RecordingImportResponse,
    RecordingUpdateRequest,
    RenderQueueResponse,
    ReorderRenderQueueRequest,
    RetryFailedResponse,
    TalkingHeadAssignRequest,
    TalkingHeadTrimRequest,
)
from outreachos_backend.rendering.config import OverlayConfig

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


@router.patch("/campaigns/{campaign_id}/quality", summary="Set the campaign quality override")
def update_campaign_quality(
    campaign_id: str,
    body: CampaignQualityUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> CampaignDetail:
    override = body.quality_override.value if body.quality_override is not None else None
    return service.update_campaign_quality(
        session,
        campaign_id,
        quality_override=override,
    )


@router.put(
    "/campaigns/{campaign_id}/overlay",
    summary="Replace the campaign's overlay geometry and styling",
)
def update_overlay_config(
    campaign_id: str,
    body: OverlayConfig,
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
) -> CampaignDetail:
    return service.update_overlay_config(session, workspace, campaign_id, body)


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


@router.put(
    "/campaigns/{campaign_id}/talking-head/trim",
    summary="Update the talking head's trim window and focal point",
)
def update_talking_head_trim(
    campaign_id: str,
    body: TalkingHeadTrimRequest,
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
) -> CampaignDetail:
    return service.update_talking_head_trim(
        session,
        workspace,
        campaign_id,
        trim_start_ms=body.trim_start_ms,
        trim_end_ms=body.trim_end_ms,
        focal_x=body.focal_x,
        focal_y=body.focal_y,
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
    workspace: WorkspaceDep,
) -> RecordingDetail:
    return service.update_recording(
        session,
        workspace,
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


@router.get(
    "/campaigns/{campaign_id}/outputs",
    summary="List un-exported renders in workspace staging",
)
def list_campaign_outputs(
    campaign_id: str,
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
) -> CampaignOutputsResponse:
    return service.get_campaign_outputs(session, workspace, campaign_id)


@router.post(
    "/campaigns/{campaign_id}/export",
    summary="Move completed renders out of staging to a destination folder",
)
def export_campaign_outputs(
    campaign_id: str,
    body: ExportAllRequest,
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
    event_bus: EventBusDep,
) -> ExportAllResponse:
    return service.export_all(
        session,
        workspace,
        event_bus,
        campaign_id,
        destination_path=body.destination_path,
    )


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


@router.post(
    "/campaigns/{campaign_id}/apply-preset",
    summary="Copy a preset's overlay config onto a campaign",
)
def apply_preset(
    campaign_id: str,
    body: ApplyPresetRequest,
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
) -> CampaignDetail:
    return service.apply_preset_to_campaign(session, workspace, campaign_id, body.preset_id)


@router.post(
    "/campaigns/{campaign_id}/cancel-queue",
    summary="Clear a campaign's queued/active render jobs and unlock its editor",
)
def cancel_queue(
    campaign_id: str,
    session: Annotated[Session, Depends(get_session)],
    event_bus: EventBusDep,
    workspace: WorkspaceDep,
) -> CampaignDetail:
    return service.cancel_queue(session, event_bus, workspace, campaign_id)


@router.get(
    "/campaigns/{campaign_id}/generate-plan",
    summary="Preview how many recordings Generate would render vs skip",
)
def get_generate_plan(
    campaign_id: str,
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
) -> GeneratePlanResponse:
    return service.get_generate_plan(session, workspace, campaign_id)


@router.post(
    "/campaigns/{campaign_id}/generate",
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue render jobs for recordings that still need rendering",
)
def generate_videos(
    campaign_id: str,
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
    worker_pool: WorkerPoolDep,
    event_bus: EventBusDep,
    body: GenerateVideosRequest | None = None,
) -> GenerateVideosResponse:
    force = body.force if body is not None else False
    return service.generate_videos(
        session,
        workspace,
        campaign_id,
        force=force,
        worker_pool=worker_pool,
        event_bus=event_bus,
    )


@router.get("/render-queue", summary="List every render job, across all campaigns, in queue order")
def list_render_queue(
    session: Annotated[Session, Depends(get_session)],
    worker_pool: WorkerPoolDep,
) -> RenderQueueResponse:
    return service.list_render_queue(session, worker_pool=worker_pool)


@router.post(
    "/render-queue/pause",
    summary="Pause the queue: finish the in-flight job, do not start the next",
)
def pause_render_queue(
    session: Annotated[Session, Depends(get_session)],
    worker_pool: WorkerPoolDep,
) -> RenderQueueResponse:
    return service.pause_render_queue(session, worker_pool=worker_pool)


@router.post(
    "/render-queue/resume",
    summary="Resume a paused render queue after crash recovery or a user pause",
)
def resume_render_queue(
    session: Annotated[Session, Depends(get_session)],
    worker_pool: WorkerPoolDep,
) -> RenderQueueResponse:
    return service.resume_render_queue(session, worker_pool=worker_pool)


@router.put(
    "/render-queue/reorder",
    summary="Reorder waiting jobs; the actively encoding job stays pinned",
)
def reorder_render_queue(
    body: ReorderRenderQueueRequest,
    session: Annotated[Session, Depends(get_session)],
    event_bus: EventBusDep,
    worker_pool: WorkerPoolDep,
) -> RenderQueueResponse:
    return service.reorder_render_queue(session, event_bus, body.job_ids, worker_pool=worker_pool)


@router.post(
    "/render-queue/jobs/{job_id}/cancel",
    summary="Cancel one queued or active job, killing it if it is running",
)
def cancel_render_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
    event_bus: EventBusDep,
    worker_pool: WorkerPoolDep,
) -> RenderQueueResponse:
    return service.cancel_render_job(session, workspace, event_bus, job_id, worker_pool=worker_pool)


@router.post(
    "/render-queue/jobs/{job_id}/retry",
    summary="Re-run a single failed job from a clean waiting state",
)
def retry_render_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
    event_bus: EventBusDep,
    worker_pool: WorkerPoolDep,
) -> RenderQueueResponse:
    return service.retry_render_job(session, workspace, event_bus, job_id, worker_pool=worker_pool)


@router.post(
    "/render-queue/retry-failed",
    summary="Re-enqueue every failed job and leave completed jobs alone",
)
def retry_failed_jobs(
    session: Annotated[Session, Depends(get_session)],
    workspace: WorkspaceDep,
    event_bus: EventBusDep,
    worker_pool: WorkerPoolDep,
) -> RetryFailedResponse:
    return service.retry_failed_jobs(session, workspace, event_bus, worker_pool=worker_pool)


@router.get("/overlay-presets", summary="List overlay presets")
def list_presets(
    session: Annotated[Session, Depends(get_session)],
) -> OverlayPresetListResponse:
    return OverlayPresetListResponse(presets=service.list_presets(session))


@router.post(
    "/overlay-presets",
    status_code=status.HTTP_201_CREATED,
    summary="Save the current overlay config as a named preset",
)
def create_preset(
    body: OverlayPresetCreateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> OverlayPresetDetail:
    return service.create_preset(session, name=body.name, overlay=body.overlay)


@router.patch("/overlay-presets/{preset_id}", summary="Rename a preset")
def rename_preset(
    preset_id: str,
    body: OverlayPresetRenameRequest,
    session: Annotated[Session, Depends(get_session)],
) -> OverlayPresetSummary:
    return service.rename_preset(session, preset_id, body.name)


@router.delete(
    "/overlay-presets/{preset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a preset",
)
def delete_preset(
    preset_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    service.delete_preset(session, preset_id)
