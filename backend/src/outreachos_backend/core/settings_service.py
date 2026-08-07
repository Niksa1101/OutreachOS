"""Application settings: read/update, cache management, render resolution."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from outreachos_backend.core.enums import JobStatus, QualityPreset
from outreachos_backend.core.errors import ApiError, ApiErrorCode
from outreachos_backend.core.models import AppSettings
from outreachos_backend.core.timeutil import utcnow_iso
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.capabilities import default_encoder_from_list, detect_encoders
from outreachos_backend.rendering.config import QualityPreset as RenderQualityPreset

__all__ = [
    "GLOBAL_QUEUE_LOCK_REASON",
    "VALID_ENCODER_OVERRIDES",
    "clear_workspace_cache",
    "compute_cache_size_bytes",
    "detected_encoder_default",
    "get_app_settings",
    "persist_ffmpeg_probe",
    "queue_has_activity",
    "resolve_encoder_override",
    "resolve_quality",
    "update_app_settings",
]

log = logging.getLogger(__name__)

GLOBAL_QUEUE_LOCK_REASON = "Changes are locked while the render queue has waiting or active jobs."

VALID_ENCODER_OVERRIDES = frozenset({"h264_nvenc", "h264_qsv", "h264_amf", "libx264"})


def get_app_settings(session: Session) -> AppSettings:
    return session.scalars(select(AppSettings).where(AppSettings.id == 1)).one()


def queue_has_activity(session: Session) -> bool:
    """True when any render job is waiting or in flight (global queue check)."""
    active_statuses = [status.value for status in JobStatus.active()]
    placeholders = ", ".join(f":s{i}" for i in range(len(active_statuses)))
    params = {f"s{i}": status for i, status in enumerate(active_statuses)}
    row = session.execute(
        text(f"SELECT 1 FROM render_jobs WHERE status IN ({placeholders}) LIMIT 1"),
        params,
    ).first()
    return row is not None


def _require_queue_idle(session: Session) -> None:
    if queue_has_activity(session):
        raise ApiError(
            ApiErrorCode.CONFLICT,
            GLOBAL_QUEUE_LOCK_REASON,
            status_code=409,
        )


def resolve_quality(session: Session, *, quality_override: str | None) -> RenderQualityPreset:
    """Campaign override wins; otherwise inherit the global preset."""
    if quality_override in ("draft", "standard", "high"):
        return quality_override  # type: ignore[return-value]
    settings = get_app_settings(session)
    return QualityPreset(settings.quality_preset).value


def resolve_encoder_override(session: Session) -> str | None:
    return get_app_settings(session).encoder_override


def detected_encoder_default(detected_encoders: str | None) -> str | None:
    """The encoder auto-detect would pick, from the cached probe list."""
    if not detected_encoders:
        return None
    try:
        available = json.loads(detected_encoders)
    except json.JSONDecodeError:
        return None
    if not isinstance(available, list) or not available:
        return None
    return default_encoder_from_list([str(item) for item in available])


def compute_cache_size_bytes(cache_root: Path) -> int:
    if not cache_root.is_dir():
        return 0
    total = 0
    for path in cache_root.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def clear_workspace_cache(session: Session, workspace: WorkspaceLayout) -> int:
    """Delete the workspace cache tree and reset campaign alpha pointers.

    Returns the byte size freed (computed before deletion).
    """
    _require_queue_idle(session)
    bytes_freed = compute_cache_size_bytes(workspace.cache)
    if workspace.cache.is_dir():
        for child in workspace.cache.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            elif child.is_file():
                child.unlink(missing_ok=True)

    session.execute(text("UPDATE campaigns SET alpha_cache_key = NULL, alpha_cache_path = NULL"))
    settings = get_app_settings(session)
    settings.updated_at = utcnow_iso()
    session.commit()
    log.info("cleared workspace cache (%d bytes)", bytes_freed)
    return bytes_freed


def persist_ffmpeg_probe(session: Session, binaries: Binaries) -> None:
    """Probe bundled FFmpeg once at boot and cache version + encoders."""
    encoders = detect_encoders(binaries)
    settings = get_app_settings(session)
    settings.ffmpeg_version = binaries.version_line
    settings.detected_encoders = json.dumps(encoders)
    settings.updated_at = utcnow_iso()
    session.commit()
    log.info("cached FFmpeg probe: %s, encoders=%s", binaries.version_line, encoders)


def update_app_settings(
    session: Session,
    *,
    quality_preset: QualityPreset | None = None,
    encoder_override: str | None = None,
    default_export_path: str | None = None,
    fields_set: set[str],
) -> AppSettings:
    settings = get_app_settings(session)

    if "quality_preset" in fields_set:
        _require_queue_idle(session)
        assert quality_preset is not None
        settings.quality_preset = quality_preset.value

    if "encoder_override" in fields_set:
        _require_queue_idle(session)
        if encoder_override is not None and encoder_override not in VALID_ENCODER_OVERRIDES:
            raise ApiError(
                ApiErrorCode.VALIDATION_ERROR,
                f"Unknown encoder {encoder_override!r}. "
                f"Choose one of: {', '.join(sorted(VALID_ENCODER_OVERRIDES))}, or auto-detect.",
                status_code=422,
            )
        settings.encoder_override = encoder_override

    if "default_export_path" in fields_set:
        if default_export_path is not None:
            resolved = Path(default_export_path).expanduser()
            if not resolved.is_absolute():
                raise ApiError(
                    ApiErrorCode.VALIDATION_ERROR,
                    "The export folder must be an absolute path.",
                    status_code=422,
                )
            settings.default_export_path = str(resolved)
        else:
            settings.default_export_path = None

    settings.updated_at = utcnow_iso()
    session.commit()
    session.refresh(settings)
    return settings
