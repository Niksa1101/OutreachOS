"""``GET/PATCH /api/v1/settings`` and ``POST /api/v1/settings/clear-cache``.

Ticket 25: global quality preset, encoder override, cache management, FFmpeg
probe facts, and the default export folder.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from outreachos_backend.core.db import get_session
from outreachos_backend.core.deps import get_workspace
from outreachos_backend.core.enums import QualityPreset
from outreachos_backend.core.models import AppSettings
from outreachos_backend.core.settings_service import (
    clear_workspace_cache,
    compute_cache_size_bytes,
    detected_encoder_default,
    get_app_settings,
    queue_has_activity,
    update_app_settings,
)
from outreachos_backend.core.workspace import WorkspaceLayout

router = APIRouter(tags=["system"])
router.redirect_slashes = False


class SettingsResponse(BaseModel):
    """DB.md §3.5, plus boot facts and live cache size."""

    quality_preset: QualityPreset
    encoder_override: str | None = Field(description="NULL means auto-detect.")
    default_export_path: str | None
    ffmpeg_version: str | None = Field(description="Cached probe of the bundled binary.")
    detected_encoders: str | None = Field(description="JSON array from the capability probe.")
    detected_encoder: str | None = Field(
        description="The encoder auto-detect would choose (NULL until probed)."
    )
    cache_size_bytes: int = Field(description="Total size of the workspace cache directory.")
    queue_busy: bool = Field(
        description=(
            "True while any render job is waiting or in flight. Quality, encoder, "
            "and Clear Cache are locked until the queue is idle."
        )
    )

    # --- from the boot report, not the database ---
    workspace_path: str
    backend_version: str
    app_version: str | None
    boot_id: str
    migration_head: str | None
    backend_log_path: str


class SettingsUpdateRequest(BaseModel):
    quality_preset: QualityPreset | None = None
    encoder_override: str | None = Field(
        default=None,
        description="NULL clears the override and restores auto-detect.",
    )
    default_export_path: str | None = Field(
        default=None,
        description="NULL clears the saved default export folder.",
    )


class ClearCacheResponse(BaseModel):
    bytes_freed: int


def _to_response(
    settings: AppSettings, request: Request, workspace: WorkspaceLayout, session: Session
) -> SettingsResponse:
    report = request.app.state.runtime.report
    return SettingsResponse(
        quality_preset=QualityPreset(settings.quality_preset),
        encoder_override=settings.encoder_override,
        default_export_path=settings.default_export_path,
        ffmpeg_version=settings.ffmpeg_version,
        detected_encoders=settings.detected_encoders,
        detected_encoder=detected_encoder_default(settings.detected_encoders),
        cache_size_bytes=compute_cache_size_bytes(workspace.cache),
        queue_busy=queue_has_activity(session),
        workspace_path=report.workspace_path,
        backend_version=report.backend_version,
        app_version=report.app_version,
        boot_id=report.boot_id,
        migration_head=report.migration_head,
        backend_log_path=report.backend_log_path,
    )


@router.get("/settings", summary="Application settings and boot facts")
def get_settings(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    workspace: Annotated[WorkspaceLayout, Depends(get_workspace)],
) -> SettingsResponse:
    settings = get_app_settings(session)
    return _to_response(settings, request, workspace, session)


@router.patch("/settings", summary="Update global application settings")
def patch_settings(
    body: SettingsUpdateRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    workspace: Annotated[WorkspaceLayout, Depends(get_workspace)],
) -> SettingsResponse:
    fields_set = body.model_fields_set
    if not fields_set:
        settings = get_app_settings(session)
        return _to_response(settings, request, workspace, session)

    settings = update_app_settings(
        session,
        quality_preset=body.quality_preset,
        encoder_override=body.encoder_override,
        default_export_path=body.default_export_path,
        fields_set=fields_set,
    )
    return _to_response(settings, request, workspace, session)


@router.post("/settings/clear-cache", summary="Clear the workspace render cache")
def post_clear_cache(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    workspace: Annotated[WorkspaceLayout, Depends(get_workspace)],
) -> ClearCacheResponse:
    bytes_freed = clear_workspace_cache(session, workspace)
    return ClearCacheResponse(bytes_freed=bytes_freed)
