"""``GET /api/v1/settings``.

Q90: read-only diagnostics in P0 — workspace path, versions, ``boot_id``,
migration head, log path. **No "Change workspace"**; that is P5, and adding the
button before the kill-and-respawn path exists would be a dead control on the
one screen users go to when they want it.

This is the first route with a database behind it, which makes it the first one
that can return 503 in degraded mode (Q84). Nothing renders it in that state —
Q104 routes to diagnostics before the shell mounts — but the dependency raises
regardless, so the invariant holds whether or not any screen respects it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from outreachos_backend.core.db import get_session
from outreachos_backend.core.enums import QualityPreset
from outreachos_backend.core.models import AppSettings

router = APIRouter(tags=["system"])
router.redirect_slashes = False


class SettingsResponse(BaseModel):
    """DB.md §3.5, plus the boot facts Settings displays alongside them."""

    quality_preset: QualityPreset
    encoder_override: str | None = Field(description="NULL means auto-detect.")
    default_export_path: str | None
    ffmpeg_version: str | None = Field(description="Cached probe result. NULL until P1 probes.")
    detected_encoders: str | None = Field(description="JSON array from the capability probe.")

    # --- from the boot report, not the database ---
    workspace_path: str
    backend_version: str
    app_version: str | None
    boot_id: str
    migration_head: str | None
    backend_log_path: str


@router.get("/settings", summary="Read-only application settings and boot facts")
def get_settings(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> SettingsResponse:
    report = request.app.state.runtime.report

    # Q60's self-healing means this cannot be `None` in practice. `.one()`
    # rather than `.first()` so that if it ever is, the failure is loud and
    # names the singleton rather than raising `AttributeError` on `None`.
    settings = session.query(AppSettings).filter(AppSettings.id == 1).one()

    return SettingsResponse(
        quality_preset=QualityPreset(settings.quality_preset),
        encoder_override=settings.encoder_override,
        default_export_path=settings.default_export_path,
        ffmpeg_version=settings.ffmpeg_version,
        detected_encoders=settings.detected_encoders,
        workspace_path=report.workspace_path,
        backend_version=report.backend_version,
        app_version=report.app_version,
        boot_id=report.boot_id,
        migration_head=report.migration_head,
        backend_log_path=report.backend_log_path,
    )
