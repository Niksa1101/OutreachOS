"""``GET /api/v1/health``.

Q113: serialises the process-level ``BootReport`` captured at startup and
**never opens a database session**. Q104 makes that a hard requirement rather
than an optimisation — the diagnostics screen renders precisely when the
database may be unusable, and every field it shows comes from here.

Q36 adds ``boot_id`` to the payload: it makes "did the sidecar silently
restart?" answerable from one field rather than inferred from a 401.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from outreachos_backend.core.boot import BootStatus, DegradedDiagnosticCode

router = APIRouter(tags=["system"])
router.redirect_slashes = False


class HealthResponse(BaseModel):
    """Everything the diagnostics screen needs from the backend side."""

    status: BootStatus = Field(
        description=(
            "`degraded` means zero database sessions are being handed out — "
            "every DB-touching route returns 503. It does not mean 'available "
            "but flagged'."
        )
    )
    boot_id: str
    backend_version: str
    app_version: str | None
    workspace_path: str
    boot_log_path: str
    backend_log_path: str
    migration_head: str | None
    migration_current: str | None
    backup_path: str | None
    detail: str | None
    diagnostic_code: DegradedDiagnosticCode | None = Field(
        default=None,
        description="Structured degraded reason when `status` is `degraded`.",
    )
    started_at: str


@router.get("/health", summary="Liveness and boot state")
def get_health(request: Request) -> HealthResponse:
    report = request.app.state.runtime.report
    return HealthResponse(
        status=report.status,
        boot_id=report.boot_id,
        backend_version=report.backend_version,
        app_version=report.app_version,
        workspace_path=report.workspace_path,
        boot_log_path=report.boot_log_path,
        backend_log_path=report.backend_log_path,
        migration_head=report.migration_head,
        migration_current=report.migration_current,
        backup_path=report.backup_path,
        detail=report.detail,
        diagnostic_code=report.diagnostic_code,
        started_at=report.started_at,
    )
