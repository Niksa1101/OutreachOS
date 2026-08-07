"""Campaign CRUD — the Video Composer service layer."""

import contextlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from outreachos_backend.core.enums import AssetRole, JobStatus, JobType, ProbeStatus
from outreachos_backend.core.errors import ApiError, ApiErrorCode
from outreachos_backend.core.events import EventBus
from outreachos_backend.core.models import new_id
from outreachos_backend.core.timeutil import utcnow_iso
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.batch_progress import compute_batch_progress
from outreachos_backend.modules.video_composer.filename_cleanup import (
    derive_company_name,
    resolve_unique_company_name,
)
from outreachos_backend.modules.video_composer.models import (
    Campaign,
    MediaAsset,
    OverlayPreset,
    RenderJob,
)
from outreachos_backend.modules.video_composer.schemas import (
    BatchProgress,
    CampaignDeleteAlphaClip,
    CampaignDeleteOutputs,
    CampaignDeletePreview,
    CampaignDetail,
    CampaignStatus,
    CampaignSummary,
    CampaignValidation,
    GeneratePlanResponse,
    GenerateVideosResponse,
    OverlayPresetDetail,
    OverlayPresetSummary,
    PreviewFrameResponse,
    RecordingDetail,
    RecordingImportRejected,
    RecordingImportResponse,
    RenderJobSummary,
    RenderQueueResponse,
    RetryFailedResponse,
    TalkingHeadDetail,
)
from outreachos_backend.modules.video_composer.validation import validate_campaign
from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.cache import (
    CacheLayout,
    alpha_cache_key,
    alpha_clip_path,
    alpha_manifest_path,
    assets_cache_key,
    preview_frame_cache_key,
    preview_frame_path,
)
from outreachos_backend.rendering.config import (
    OverlayConfig,
    QualityPreset,
    TalkingHeadConfig,
    upgrade_overlay_config,
)
from outreachos_backend.rendering.errors import RenderFatalError, RenderProcessError
from outreachos_backend.rendering.frame_extract import extract_frame
from outreachos_backend.rendering.geometry import clamp_overlay_config
from outreachos_backend.rendering.probe import ProbeResult, probe_media
from outreachos_backend.rendering.process import request_cancel
from outreachos_backend.rendering.queue.pool import WorkerPool

DEFAULT_CAMPAIGN_NAME = "Untitled campaign"

PRE_SETTINGS_DEFAULT_QUALITY_PRESET: QualityPreset = "standard"
"""Ticket 15: fixed until ticket 25 introduces Settings.

Deliberately **not** read from ``app_settings.quality_preset`` even though that
row/column already exists and already defaults to ``"standard"`` — this value
is pinned in code so ticket 25's work is wiring a value through rather than
changing render behaviour. A campaign's own ``quality_override`` still wins
when set; this is only the fallback.
"""

PREVIEW_FRAME_TARGET_MS = 2000
"""Ticket 09: extract at 00:02, clamped to the recording's midpoint when shorter."""

LOCK_REASON = "Editing is locked while this campaign has queued or active render jobs."
"""Ticket 21 / PRD §6.5's exact wording — shown verbatim by the banner."""


def is_campaign_locked(session: Session, campaign_id: str) -> bool:
    """DB.md §6's editor lock check: any queued or active job for this campaign."""
    return (
        session.scalar(
            select(RenderJob.id)
            .where(
                RenderJob.campaign_id == campaign_id,
                RenderJob.status.in_([status.value for status in JobStatus.active()]),
            )
            .limit(1)
        )
        is not None
    )


def _require_unlocked(session: Session, campaign_id: str) -> None:
    if is_campaign_locked(session, campaign_id):
        raise ApiError(
            ApiErrorCode.CONFLICT,
            LOCK_REASON,
            status_code=409,
        )


def default_overlay_config() -> tuple[str, int]:
    """Return ``(overlay_config_json, overlay_schema_version)`` for a new campaign."""
    overlay = OverlayConfig()
    return overlay.model_dump_json(), overlay.schema_version


def _recording_count(session: Session, campaign_id: str) -> int:
    count = session.scalar(
        select(func.count())
        .select_from(MediaAsset)
        .where(
            MediaAsset.campaign_id == campaign_id,
            MediaAsset.role == AssetRole.SCREEN_RECORDING.value,
        )
    )
    return int(count or 0)


def _last_rendered_at(session: Session, campaign_id: str) -> str | None:
    return session.scalar(
        select(func.max(MediaAsset.last_rendered_at)).where(
            MediaAsset.campaign_id == campaign_id,
            MediaAsset.last_rendered_at.is_not(None),
        )
    )


def _compute_status(
    last_rendered_at: str | None,
    validation: CampaignValidation,
) -> CampaignStatus:
    if validation.can_generate:
        if last_rendered_at is not None:
            return CampaignStatus.HAS_RENDERED
        return CampaignStatus.READY
    if last_rendered_at is not None:
        return CampaignStatus.BLOCKED
    return CampaignStatus.DRAFT


def _to_summary(session: Session, campaign: Campaign) -> CampaignSummary:
    last_rendered_at = _last_rendered_at(session, campaign.id)
    talking_head = _get_talking_head(session, campaign.id)
    recordings = _list_recordings(session, campaign.id)
    validation = validate_campaign(
        talking_head=talking_head,
        recordings=recordings,
    )
    return CampaignSummary(
        id=campaign.id,
        name=campaign.name,
        recording_count=len(recordings),
        last_rendered_at=last_rendered_at,
        status=_compute_status(last_rendered_at, validation),
    )


def _get_talking_head(session: Session, campaign_id: str) -> MediaAsset | None:
    return session.scalar(
        select(MediaAsset).where(
            MediaAsset.campaign_id == campaign_id,
            MediaAsset.role == AssetRole.TALKING_HEAD.value,
        )
    )


def _list_recordings(session: Session, campaign_id: str) -> list[MediaAsset]:
    return list(
        session.scalars(
            select(MediaAsset)
            .where(
                MediaAsset.campaign_id == campaign_id,
                MediaAsset.role == AssetRole.SCREEN_RECORDING.value,
            )
            .order_by(MediaAsset.sort_order, MediaAsset.created_at)
        ).all()
    )


def _to_recording_detail(asset: MediaAsset) -> RecordingDetail:
    return RecordingDetail(
        id=asset.id,
        source_path=asset.source_path,
        source_filename=asset.source_filename,
        file_missing=bool(asset.file_missing),
        company_name=asset.company_name or "Untitled",
        output_basename=asset.output_basename or "Untitled",
        probe_status=asset.probe_status,
        probe_error=asset.probe_error,
        duration_ms=asset.duration_ms,
        width=asset.width,
        height=asset.height,
        fps=asset.fps,
        video_codec=asset.video_codec,
        has_audio=bool(asset.has_audio) if asset.has_audio is not None else None,
        sort_order=asset.sort_order,
    )


def _to_talking_head_detail(asset: MediaAsset) -> TalkingHeadDetail:
    assert asset.duration_ms is not None
    assert asset.width is not None
    assert asset.height is not None
    assert asset.fps is not None
    assert asset.video_codec is not None
    assert asset.has_audio is not None
    assert asset.trim_start_ms is not None
    assert asset.trim_end_ms is not None
    assert asset.focal_x is not None
    assert asset.focal_y is not None

    return TalkingHeadDetail(
        id=asset.id,
        source_path=asset.source_path,
        source_filename=asset.source_filename,
        file_missing=bool(asset.file_missing),
        duration_ms=asset.duration_ms,
        width=asset.width,
        height=asset.height,
        fps=asset.fps,
        video_codec=asset.video_codec,
        has_audio=bool(asset.has_audio),
        trim_start_ms=asset.trim_start_ms,
        trim_end_ms=asset.trim_end_ms,
        focal_x=asset.focal_x,
        focal_y=asset.focal_y,
    )


def _to_detail(session: Session, campaign: Campaign) -> CampaignDetail:
    last_rendered_at = _last_rendered_at(session, campaign.id)
    talking_head = _get_talking_head(session, campaign.id)
    recording_assets = _list_recordings(session, campaign.id)
    validation = validate_campaign(
        talking_head=talking_head,
        recordings=recording_assets,
    )
    recordings = [_to_recording_detail(asset) for asset in recording_assets]
    locked = is_campaign_locked(session, campaign.id)
    return CampaignDetail(
        id=campaign.id,
        name=campaign.name,
        recording_count=len(recording_assets),
        last_rendered_at=last_rendered_at,
        status=_compute_status(last_rendered_at, validation),
        overlay_config=campaign.overlay_config,
        overlay_schema_version=campaign.overlay_schema_version,
        talking_head=_to_talking_head_detail(talking_head) if talking_head else None,
        recordings=recordings,
        validation=validation,
        is_locked=locked,
        lock_reason=LOCK_REASON if locked else None,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


def list_campaigns(session: Session) -> list[CampaignSummary]:
    campaigns = session.scalars(select(Campaign).order_by(Campaign.updated_at.desc())).all()
    return [_to_summary(session, campaign) for campaign in campaigns]


def _existing_campaign_names(session: Session) -> set[str]:
    rows = session.scalars(select(Campaign.name)).all()
    return {str(name) for name in rows}


def _clone_talking_head(source: MediaAsset, *, campaign_id: str) -> MediaAsset:
    return MediaAsset(
        campaign_id=campaign_id,
        role=AssetRole.TALKING_HEAD.value,
        source_path=source.source_path,
        source_filename=source.source_filename,
        probe_status=source.probe_status,
        probe_error=source.probe_error,
        duration_ms=source.duration_ms,
        width=source.width,
        height=source.height,
        fps=source.fps,
        video_codec=source.video_codec,
        has_audio=source.has_audio,
        file_missing=source.file_missing,
        last_verified_at=source.last_verified_at,
        trim_start_ms=source.trim_start_ms,
        trim_end_ms=source.trim_end_ms,
        focal_x=source.focal_x,
        focal_y=source.focal_y,
        sort_order=source.sort_order,
    )


def duplicate_campaign(session: Session, campaign_id: str) -> CampaignDetail:
    source = _require_campaign(session, campaign_id)
    duplicate_name = resolve_unique_company_name(source.name, _existing_campaign_names(session))

    duplicate = Campaign(
        name=duplicate_name,
        overlay_config=source.overlay_config,
        overlay_schema_version=source.overlay_schema_version,
        quality_override=source.quality_override,
        default_export_path=source.default_export_path,
    )
    session.add(duplicate)
    session.flush()

    talking_head = _get_talking_head(session, campaign_id)
    if talking_head is not None:
        session.add(_clone_talking_head(talking_head, campaign_id=duplicate.id))

    session.commit()
    session.refresh(duplicate)
    return _to_detail(session, duplicate)


def create_campaign(session: Session, *, name: str | None = None) -> CampaignDetail:
    overlay_config, overlay_schema_version = default_overlay_config()
    campaign = Campaign(
        name=(name or DEFAULT_CAMPAIGN_NAME).strip() or DEFAULT_CAMPAIGN_NAME,
        overlay_config=overlay_config,
        overlay_schema_version=overlay_schema_version,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return _to_detail(session, campaign)


def _verify_asset_link_health(asset: MediaAsset, *, now: str) -> bool:
    """Update ``file_missing`` and ``last_verified_at`` for one asset.

    Returns True when ``file_missing`` changed.
    """
    missing = 0 if Path(asset.source_path).is_file() else 1
    changed = asset.file_missing != missing
    asset.file_missing = missing
    asset.last_verified_at = now
    return changed


def _verify_campaign_link_health(session: Session, campaign_id: str) -> None:
    """Refresh persisted link-health for every asset in a campaign."""
    assets = session.scalars(select(MediaAsset).where(MediaAsset.campaign_id == campaign_id)).all()
    if not assets:
        return

    now = utcnow_iso()
    changed = False
    for asset in assets:
        if _verify_asset_link_health(asset, now=now):
            changed = True

    if changed:
        campaign = session.get(Campaign, campaign_id)
        assert campaign is not None
        campaign.updated_at = now

    session.commit()


def get_campaign(session: Session, campaign_id: str) -> CampaignDetail:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise ApiError(
            ApiErrorCode.NOT_FOUND,
            "That campaign does not exist.",
            status_code=404,
        )
    _verify_campaign_link_health(session, campaign_id)
    session.refresh(campaign)
    return _to_detail(session, campaign)


def rename_campaign(session: Session, campaign_id: str, name: str) -> CampaignDetail:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise ApiError(
            ApiErrorCode.NOT_FOUND,
            "That campaign does not exist.",
            status_code=404,
        )

    trimmed = name.strip()
    if not trimmed:
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "A campaign name cannot be empty.",
            status_code=422,
        )

    campaign.name = trimmed
    campaign.updated_at = utcnow_iso()
    session.commit()
    session.refresh(campaign)
    return _to_detail(session, campaign)


def update_overlay_config(
    session: Session,
    workspace: WorkspaceLayout,
    campaign_id: str,
    overlay: OverlayConfig,
) -> CampaignDetail:
    """Persist a new overlay config, clamped server-side (PRD §6.2).

    Ticket 11: the frontend clamps on every input path for immediate visual
    feedback, but the server is the actual source of truth — it re-clamps
    rather than trusting the client, so a stale or bypassed frontend can never
    persist an off-frame or inverted overlay.
    """
    campaign = _require_campaign(session, campaign_id)
    _require_unlocked(session, campaign_id)
    clamped = clamp_overlay_config(overlay)
    campaign.overlay_config = clamped.model_dump_json()
    campaign.overlay_schema_version = clamped.schema_version
    _invalidate_alpha_cache(workspace, campaign)
    campaign.updated_at = utcnow_iso()
    session.commit()
    session.refresh(campaign)
    return _to_detail(session, campaign)


def _resolve_source_path(source_path: str) -> Path:
    path = Path(source_path)
    if not path.is_absolute():
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "The file path must be absolute.",
            status_code=422,
        )
    return path.resolve()


def _probe_source_video(binaries: Binaries, path: Path) -> ProbeResult:
    outcome = _probe_source_video_soft(binaries, path)
    if outcome.error is not None:
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            outcome.error,
            status_code=422,
        )
    assert outcome.probe is not None
    return outcome.probe


def _invalidate_alpha_cache(workspace: WorkspaceLayout, campaign: Campaign) -> None:
    for path in _alpha_cache_paths(workspace, campaign):
        _safe_unlink(workspace, path)
    campaign.alpha_cache_key = None
    campaign.alpha_cache_path = None


def assign_talking_head(
    session: Session,
    binaries: Binaries,
    workspace: WorkspaceLayout,
    campaign_id: str,
    *,
    source_path: str,
) -> CampaignDetail:
    campaign = _require_campaign(session, campaign_id)
    _require_unlocked(session, campaign_id)
    resolved = _resolve_source_path(source_path)
    probe = _probe_source_video(binaries, resolved)

    duration_ms = max(1, round(probe.duration_s * 1000))
    now = utcnow_iso()
    key = str(resolved)

    existing = _get_talking_head(session, campaign_id)
    if key in _existing_campaign_paths(
        session,
        campaign_id,
        exclude_asset_id=existing.id if existing else None,
    ):
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "That file is already in this campaign.",
            status_code=422,
        )

    if existing is not None:
        session.delete(existing)
        session.flush()

    asset = MediaAsset(
        campaign_id=campaign_id,
        role=AssetRole.TALKING_HEAD.value,
        source_path=key,
        source_filename=resolved.name,
        probe_status=ProbeStatus.OK.value,
        duration_ms=duration_ms,
        width=probe.display_width,
        height=probe.display_height,
        fps=probe.fps,
        video_codec=probe.codec_name,
        has_audio=1 if probe.has_audio else 0,
        file_missing=0,
        last_verified_at=now,
        trim_start_ms=0,
        trim_end_ms=duration_ms,
        focal_x=0.5,
        focal_y=0.5,
    )
    session.add(asset)
    _invalidate_alpha_cache(workspace, campaign)
    campaign.updated_at = now
    session.commit()
    session.refresh(campaign)
    return _to_detail(session, campaign)


def _clamp_trim_window(
    trim_start_ms: int, trim_end_ms: int, duration_ms: int | None
) -> tuple[int, int]:
    """Never inverted, never past source bounds, never zero-length (ticket 13).

    Re-clamped server-side rather than trusted, mirroring
    ``update_overlay_config`` — the frontend clamps for immediate feedback, but
    the server is the actual source of truth.
    """
    if not duration_ms:
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "This talking head has no known duration.",
            status_code=422,
        )
    start = max(0, min(trim_start_ms, duration_ms - 1))
    end = max(start + 1, min(trim_end_ms, duration_ms))
    return start, end


def update_talking_head_trim(
    session: Session,
    workspace: WorkspaceLayout,
    campaign_id: str,
    *,
    trim_start_ms: int,
    trim_end_ms: int,
    focal_x: float,
    focal_y: float,
) -> CampaignDetail:
    campaign = _require_campaign(session, campaign_id)
    _require_unlocked(session, campaign_id)
    talking_head = _get_talking_head(session, campaign_id)
    if talking_head is None:
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "This campaign has no talking head to trim.",
            status_code=422,
        )

    start, end = _clamp_trim_window(trim_start_ms, trim_end_ms, talking_head.duration_ms)
    talking_head.trim_start_ms = start
    talking_head.trim_end_ms = end
    talking_head.focal_x = max(0.0, min(1.0, focal_x))
    talking_head.focal_y = max(0.0, min(1.0, focal_y))

    _invalidate_alpha_cache(workspace, campaign)
    campaign.updated_at = utcnow_iso()
    session.commit()
    session.refresh(campaign)
    return _to_detail(session, campaign)


@dataclass(frozen=True)
class _ProbeOutcome:
    probe: ProbeResult | None
    error: str | None
    missing: bool


def _probe_source_video_soft(binaries: Binaries, path: Path) -> _ProbeOutcome:
    if not path.is_file():
        return _ProbeOutcome(None, "That file could not be found.", missing=True)

    try:
        probe = probe_media(binaries, str(path))
    except RenderFatalError as exc:
        message = str(exc)
        if "No video stream" in message:
            return _ProbeOutcome(None, "That file is not a video.", missing=False)
        return _ProbeOutcome(None, "That file could not be read as a video.", missing=False)

    return _ProbeOutcome(probe, None, missing=False)


def _next_sort_order(session: Session, campaign_id: str) -> int:
    current_max = session.scalar(
        select(func.max(MediaAsset.sort_order)).where(
            MediaAsset.campaign_id == campaign_id,
            MediaAsset.role == AssetRole.SCREEN_RECORDING.value,
        )
    )
    return int(current_max or -1) + 1


def _existing_campaign_paths(
    session: Session,
    campaign_id: str,
    *,
    exclude_asset_id: str | None = None,
) -> set[str]:
    query = select(MediaAsset.source_path).where(MediaAsset.campaign_id == campaign_id)
    if exclude_asset_id is not None:
        query = query.where(MediaAsset.id != exclude_asset_id)
    rows = session.scalars(query).all()
    return {str(path) for path in rows}


def _existing_company_names(session: Session, campaign_id: str) -> set[str]:
    rows = session.scalars(
        select(MediaAsset.company_name).where(
            MediaAsset.campaign_id == campaign_id,
            MediaAsset.role == AssetRole.SCREEN_RECORDING.value,
            MediaAsset.company_name.is_not(None),
        )
    ).all()
    return {str(name) for name in rows}


def import_recordings(
    session: Session,
    binaries: Binaries,
    campaign_id: str,
    *,
    source_paths: list[str],
) -> RecordingImportResponse:
    campaign = _require_campaign(session, campaign_id)
    rejected: list[RecordingImportRejected] = []
    failed: list[RecordingImportRejected] = []
    added: list[RecordingDetail] = []

    existing_paths = _existing_campaign_paths(session, campaign_id)
    seen_paths: set[str] = set(existing_paths)
    taken_names = _existing_company_names(session, campaign_id)
    sort_order = _next_sort_order(session, campaign_id)
    now = utcnow_iso()

    candidates: list[tuple[str, Path]] = []
    for raw_path in source_paths:
        try:
            resolved = _resolve_source_path(raw_path)
        except ApiError as exc:
            rejected.append(RecordingImportRejected(source_path=raw_path, message=exc.message))
            continue

        key = str(resolved)
        if key in seen_paths:
            rejected.append(
                RecordingImportRejected(
                    source_path=key,
                    message="That file is already in this campaign.",
                )
            )
            continue

        seen_paths.add(key)
        candidates.append((key, resolved))

    if not candidates:
        return RecordingImportResponse(
            added=[],
            rejected=rejected,
            failed=failed,
            recording_count=_recording_count(session, campaign_id),
        )

    probe_outcomes: dict[str, _ProbeOutcome] = {}
    with ThreadPoolExecutor(max_workers=min(len(candidates), 8)) as pool:
        futures = {
            pool.submit(_probe_source_video_soft, binaries, path): key for key, path in candidates
        }
        for future in as_completed(futures):
            key = futures[future]
            probe_outcomes[key] = future.result()

    assets: list[MediaAsset] = []
    for key, resolved in candidates:
        outcome = probe_outcomes[key]
        base_name = derive_company_name(resolved.name)
        company_name = resolve_unique_company_name(base_name, taken_names)
        taken_names.add(company_name)
        auto_suffixed = 1 if company_name != base_name else 0

        if outcome.error is not None:
            asset = MediaAsset(
                campaign_id=campaign_id,
                role=AssetRole.SCREEN_RECORDING.value,
                source_path=key,
                source_filename=resolved.name,
                company_name=company_name,
                output_basename=company_name,
                sort_order=sort_order,
                probe_status=ProbeStatus.FAILED.value,
                probe_error=outcome.error,
                file_missing=1 if outcome.missing else 0,
                name_auto_suffixed=auto_suffixed,
                last_verified_at=now,
            )
            failed.append(RecordingImportRejected(source_path=key, message=outcome.error))
        else:
            assert outcome.probe is not None
            probe = outcome.probe
            duration_ms = max(1, round(probe.duration_s * 1000))
            asset = MediaAsset(
                campaign_id=campaign_id,
                role=AssetRole.SCREEN_RECORDING.value,
                source_path=key,
                source_filename=resolved.name,
                company_name=company_name,
                output_basename=company_name,
                sort_order=sort_order,
                probe_status=ProbeStatus.OK.value,
                duration_ms=duration_ms,
                width=probe.display_width,
                height=probe.display_height,
                fps=probe.fps,
                video_codec=probe.codec_name,
                has_audio=1 if probe.has_audio else 0,
                file_missing=0,
                name_auto_suffixed=auto_suffixed,
                last_verified_at=now,
            )

        session.add(asset)
        assets.append(asset)
        sort_order += 1

    if assets:
        campaign.updated_at = now
        session.commit()
        for asset in assets:
            session.refresh(asset)
        added = [_to_recording_detail(asset) for asset in assets]

    return RecordingImportResponse(
        added=added,
        rejected=rejected,
        failed=failed,
        recording_count=_recording_count(session, campaign_id),
    )


def _require_recording(session: Session, campaign_id: str, recording_id: str) -> MediaAsset:
    asset = session.get(MediaAsset, recording_id)
    if (
        asset is None
        or asset.campaign_id != campaign_id
        or asset.role != AssetRole.SCREEN_RECORDING.value
    ):
        raise ApiError(
            ApiErrorCode.NOT_FOUND,
            "That recording does not exist.",
            status_code=404,
        )
    return asset


def update_recording(
    session: Session,
    campaign_id: str,
    recording_id: str,
    *,
    company_name: str,
) -> RecordingDetail:
    campaign = _require_campaign(session, campaign_id)
    asset = _require_recording(session, campaign_id, recording_id)

    trimmed = company_name.strip()
    if not trimmed:
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "A company name cannot be empty.",
            status_code=422,
        )

    taken = _existing_company_names(session, campaign_id)
    if asset.company_name is not None:
        taken.discard(asset.company_name)
    resolved = resolve_unique_company_name(trimmed, taken)
    auto_suffixed = 1 if resolved != trimmed else 0

    asset.company_name = resolved
    asset.output_basename = resolved
    asset.name_auto_suffixed = auto_suffixed
    campaign.updated_at = utcnow_iso()
    session.commit()
    session.refresh(asset)
    return _to_recording_detail(asset)


def delete_recording(session: Session, campaign_id: str, recording_id: str) -> None:
    campaign = _require_campaign(session, campaign_id)
    asset = _require_recording(session, campaign_id, recording_id)

    session.delete(asset)
    campaign.updated_at = utcnow_iso()
    session.commit()


def _require_asset(session: Session, campaign_id: str, asset_id: str) -> MediaAsset:
    asset = session.get(MediaAsset, asset_id)
    if asset is None or asset.campaign_id != campaign_id:
        raise ApiError(
            ApiErrorCode.NOT_FOUND,
            "That asset does not exist.",
            status_code=404,
        )
    return asset


def _apply_probe_to_asset(asset: MediaAsset, probe: ProbeResult) -> None:
    duration_ms = max(1, round(probe.duration_s * 1000))
    asset.probe_status = ProbeStatus.OK.value
    asset.probe_error = None
    asset.duration_ms = duration_ms
    asset.width = probe.display_width
    asset.height = probe.display_height
    asset.fps = probe.fps
    asset.video_codec = probe.codec_name
    asset.has_audio = 1 if probe.has_audio else 0

    if asset.role == AssetRole.TALKING_HEAD.value:
        if asset.trim_start_ms is None:
            asset.trim_start_ms = 0
        if asset.trim_end_ms is None or asset.trim_end_ms > duration_ms:
            asset.trim_end_ms = duration_ms
        if asset.trim_start_ms >= asset.trim_end_ms:
            asset.trim_start_ms = 0
            asset.trim_end_ms = duration_ms


def relocate_asset(
    session: Session,
    binaries: Binaries,
    workspace: WorkspaceLayout,
    campaign_id: str,
    asset_id: str,
    *,
    source_path: str,
) -> CampaignDetail:
    campaign = _require_campaign(session, campaign_id)
    asset = _require_asset(session, campaign_id, asset_id)
    resolved = _resolve_source_path(source_path)
    key = str(resolved)

    if key in _existing_campaign_paths(session, campaign_id, exclude_asset_id=asset_id):
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "That file is already in this campaign.",
            status_code=422,
        )

    probe = _probe_source_video(binaries, resolved)
    now = utcnow_iso()

    asset.source_path = key
    asset.source_filename = resolved.name
    asset.file_missing = 0
    asset.last_verified_at = now
    _apply_probe_to_asset(asset, probe)
    if asset.role == AssetRole.TALKING_HEAD.value:
        _invalidate_alpha_cache(workspace, campaign)
    campaign.updated_at = now
    session.commit()
    session.refresh(campaign)
    return _to_detail(session, campaign)


def _require_campaign(session: Session, campaign_id: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise ApiError(
            ApiErrorCode.NOT_FOUND,
            "That campaign does not exist.",
            status_code=404,
        )
    return campaign


def _alpha_cache_paths(workspace: WorkspaceLayout, campaign: Campaign) -> list[Path]:
    paths: list[Path] = []

    if campaign.alpha_cache_path:
        clip = workspace.root / campaign.alpha_cache_path
        paths.append(clip)
        paths.append(clip.with_name(f"{clip.stem}.manifest.json"))

    if campaign.alpha_cache_key:
        layout = CacheLayout(root=workspace.cache)
        paths.append(alpha_clip_path(layout, campaign.alpha_cache_key))
        paths.append(alpha_manifest_path(layout, campaign.alpha_cache_key))

    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _staged_output_paths(workspace: WorkspaceLayout, campaign_id: str) -> list[Path]:
    output_dir = workspace.outputs / campaign_id
    if not output_dir.is_dir():
        return []
    return [path for path in output_dir.rglob("*") if path.is_file()]


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size if path.is_file() else None
    except OSError:
        return None


def _sum_file_sizes(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        size = _file_size(path)
        if size is not None:
            total += size
    return total


def _present_alpha_clip(paths: list[Path]) -> CampaignDeleteAlphaClip:
    clip_paths = [path for path in paths if path.suffix == ".mov" and path.is_file()]
    if not clip_paths:
        return CampaignDeleteAlphaClip(present=False, size_bytes=None)
    return CampaignDeleteAlphaClip(
        present=True,
        size_bytes=_sum_file_sizes(clip_paths),
    )


def _preview_frame_timestamp_ms(duration_ms: int) -> int:
    return min(PREVIEW_FRAME_TARGET_MS, duration_ms // 2)


def get_preview_frame(
    session: Session,
    binaries: Binaries,
    workspace: WorkspaceLayout,
    campaign_id: str,
) -> PreviewFrameResponse:
    """The split-view preview's background frame — ticket 09.

    Not folded into ``_to_detail``: extraction can spawn FFmpeg, and campaign
    detail's only other side effect (link-health verification) is a plain
    ``stat()``. Keeping this its own endpoint keeps ``GET /campaigns/{id}``
    cheap and side-effect-bounded the way it already is.
    """
    _require_campaign(session, campaign_id)
    recordings = _list_recordings(session, campaign_id)
    if not recordings:
        return PreviewFrameResponse(available=False)

    first = recordings[0]
    resolved = Path(first.source_path)
    if not resolved.is_file():
        return PreviewFrameResponse(
            available=False,
            error="The first recording's file could not be found.",
        )

    if first.probe_status != ProbeStatus.OK.value or first.duration_ms is None:
        return PreviewFrameResponse(
            available=False,
            error=first.probe_error or "The first recording could not be read as a video.",
        )

    timestamp_ms = _preview_frame_timestamp_ms(first.duration_ms)
    layout = CacheLayout(root=workspace.cache)
    frame_key = preview_frame_cache_key(resolved, timestamp_ms)
    dest = preview_frame_path(layout, frame_key)

    if not dest.is_file():
        try:
            extract_frame(binaries, resolved, timestamp_ms / 1000.0, dest)
        except (RenderProcessError, RenderFatalError):
            return PreviewFrameResponse(
                available=False,
                error="Could not extract a preview frame from the first recording.",
            )

    return PreviewFrameResponse(available=True, frame_path=str(dest))


def get_delete_preview(
    session: Session,
    workspace: WorkspaceLayout,
    campaign_id: str,
) -> CampaignDeletePreview:
    campaign = _require_campaign(session, campaign_id)
    assets = session.scalars(select(MediaAsset).where(MediaAsset.campaign_id == campaign_id)).all()

    recording_count = sum(1 for asset in assets if asset.role == AssetRole.SCREEN_RECORDING.value)
    talking_head_count = sum(1 for asset in assets if asset.role == AssetRole.TALKING_HEAD.value)
    output_paths = _staged_output_paths(workspace, campaign_id)

    return CampaignDeletePreview(
        campaign_id=campaign.id,
        campaign_name=campaign.name,
        asset_count=len(assets),
        recording_count=recording_count,
        talking_head_count=talking_head_count,
        alpha_clip=_present_alpha_clip(_alpha_cache_paths(workspace, campaign)),
        outputs=CampaignDeleteOutputs(
            count=len(output_paths),
            total_size_bytes=_sum_file_sizes(output_paths),
        ),
    )


def _safe_unlink(workspace: WorkspaceLayout, path: Path) -> None:
    """Unlink a workspace-relative file, retrying briefly on Windows lock races.

    Cancel kills FFmpeg and unlinks from the API thread in the same breath; on
    Windows the handle may still be open for a few hundred milliseconds.
    Ticket 19 requires the partial to actually disappear, so ``PermissionError``
    is retried (~5 x 100 ms) before we give up.
    """
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(workspace.root.resolve()):
            return
        if not resolved.is_file():
            return
        for attempt in range(5):
            try:
                resolved.unlink()
                return
            except PermissionError:
                if attempt == 4:
                    return
                time.sleep(0.1)
            except OSError:
                return
    except OSError:
        return


def _remove_empty_dirs(workspace: WorkspaceLayout, path: Path) -> None:
    try:
        resolved = path.resolve()
        root = workspace.root.resolve()
        if not resolved.is_relative_to(root):
            return
        if not resolved.is_dir():
            return
        for child in sorted(resolved.rglob("*"), reverse=True):
            if child.is_dir():
                with contextlib.suppress(OSError):
                    child.rmdir()
        with contextlib.suppress(OSError):
            resolved.rmdir()
    except OSError:
        return


def delete_campaign(
    session: Session,
    workspace: WorkspaceLayout,
    campaign_id: str,
) -> None:
    campaign = _require_campaign(session, campaign_id)
    alpha_paths = _alpha_cache_paths(workspace, campaign)
    output_paths = _staged_output_paths(workspace, campaign_id)
    output_dir = workspace.outputs / campaign_id

    session.delete(campaign)
    session.commit()

    for path in (*alpha_paths, *output_paths):
        _safe_unlink(workspace, path)

    _remove_empty_dirs(workspace, output_dir)


def _to_preset_summary(preset: OverlayPreset) -> OverlayPresetSummary:
    return OverlayPresetSummary(
        id=preset.id,
        name=preset.name,
        overlay_schema_version=preset.overlay_schema_version,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


def _to_preset_detail(preset: OverlayPreset) -> OverlayPresetDetail:
    return OverlayPresetDetail(
        overlay_config=preset.overlay_config,
        **_to_preset_summary(preset).model_dump(),
    )


def _require_preset(session: Session, preset_id: str) -> OverlayPreset:
    preset = session.get(OverlayPreset, preset_id)
    if preset is None:
        raise ApiError(
            ApiErrorCode.NOT_FOUND,
            "That preset does not exist.",
            status_code=404,
        )
    return preset


def _require_unique_preset_name(
    session: Session, name: str, *, exclude_id: str | None = None
) -> None:
    query = select(OverlayPreset.id).where(OverlayPreset.name == name)
    if exclude_id is not None:
        query = query.where(OverlayPreset.id != exclude_id)
    if session.scalar(query) is not None:
        raise ApiError(
            ApiErrorCode.CONFLICT,
            f'A preset named "{name}" already exists.',
            status_code=409,
        )


def list_presets(session: Session) -> list[OverlayPresetSummary]:
    presets = session.scalars(select(OverlayPreset).order_by(OverlayPreset.name)).all()
    return [_to_preset_summary(preset) for preset in presets]


def create_preset(session: Session, *, name: str, overlay: OverlayConfig) -> OverlayPresetDetail:
    trimmed = name.strip()
    if not trimmed:
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "A preset name cannot be empty.",
            status_code=422,
        )

    _require_unique_preset_name(session, trimmed)

    clamped = clamp_overlay_config(overlay)
    preset = OverlayPreset(
        name=trimmed,
        overlay_config=clamped.model_dump_json(),
        overlay_schema_version=clamped.schema_version,
    )
    session.add(preset)
    session.commit()
    session.refresh(preset)
    return _to_preset_detail(preset)


def rename_preset(session: Session, preset_id: str, name: str) -> OverlayPresetSummary:
    preset = _require_preset(session, preset_id)

    trimmed = name.strip()
    if not trimmed:
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "A preset name cannot be empty.",
            status_code=422,
        )

    _require_unique_preset_name(session, trimmed, exclude_id=preset_id)

    preset.name = trimmed
    preset.updated_at = utcnow_iso()
    session.commit()
    session.refresh(preset)
    return _to_preset_summary(preset)


def delete_preset(session: Session, preset_id: str) -> None:
    preset = _require_preset(session, preset_id)
    session.delete(preset)
    session.commit()


def apply_preset_to_campaign(
    session: Session,
    workspace: WorkspaceLayout,
    campaign_id: str,
    preset_id: str,
) -> CampaignDetail:
    """Copy a preset's overlay config onto a campaign (PRD §6.2, ticket 14).

    There is no live link kept between campaign and preset — this writes a
    plain snapshot, upgraded to the current overlay schema and re-clamped the
    same way ``update_overlay_config`` clamps a direct edit, so an older
    preset can never corrupt a campaign's overlay on apply.
    """
    campaign = _require_campaign(session, campaign_id)
    _require_unlocked(session, campaign_id)
    preset = _require_preset(session, preset_id)

    try:
        upgraded = upgrade_overlay_config(
            json.loads(preset.overlay_config),
            from_version=preset.overlay_schema_version,
        )
    except ValueError as exc:
        # `rendering/` must not import the API error module (import-boundary
        # test), so the version check there raises a bare ValueError — this
        # is the crossing point that turns it into a proper 422.
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "That preset was saved with an overlay schema version this build doesn't recognize.",
            status_code=422,
        ) from exc
    clamped = clamp_overlay_config(upgraded)
    campaign.overlay_config = clamped.model_dump_json()
    campaign.overlay_schema_version = clamped.schema_version
    _invalidate_alpha_cache(workspace, campaign)
    campaign.updated_at = utcnow_iso()
    session.commit()
    session.refresh(campaign)
    return _to_detail(session, campaign)


def cancel_queue(
    session: Session,
    event_bus: EventBus,
    workspace: WorkspaceLayout,
    campaign_id: str,
) -> CampaignDetail:
    """Ticket 19/21: clear a campaign's queued/active jobs and unlock its editor.

    Kills any in-flight FFmpeg for this campaign, deletes partial outputs, and
    removes every waiting/active row so ``is_campaign_locked`` sees nothing busy.
    Completed and failed jobs are left alone; they are not what holds the lock.
    """
    campaign = _require_campaign(session, campaign_id)
    active_statuses = [status.value for status in JobStatus.active()]
    interrupted = {status.value for status in JobStatus.interrupted()}
    jobs = session.scalars(
        select(RenderJob).where(
            RenderJob.campaign_id == campaign_id,
            RenderJob.status.in_(active_statuses),
        )
    ).all()
    for job in jobs:
        if job.status in interrupted:
            request_cancel(job.id)
        _delete_job_partials(workspace, job)
        session.delete(job)

    campaign.updated_at = utcnow_iso()
    session.commit()
    session.refresh(campaign)

    event_bus.campaign_lock_changed(campaign_id, locked=False)
    # Ticket 18: badge must clear when the queue goes idle, without polling.
    event_bus.batch_progress_changed(batch_event_payload(session))
    return _to_detail(session, campaign)


def _to_job_summary(campaign_name: str, job: RenderJob) -> RenderJobSummary:
    return RenderJobSummary(
        id=job.id,
        campaign_id=job.campaign_id,
        campaign_name=campaign_name,
        asset_id=job.asset_id,
        job_type=job.job_type,
        status=job.status,
        queue_position=job.queue_position,
        progress_pct=job.progress_pct,
        depends_on_job_id=job.depends_on_job_id,
        output_filename=job.output_filename,
        error_message=job.error_message,
        error_details=job.error_details,
        ffmpeg_command=job.ffmpeg_command,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def job_event_payload(campaign_name: str, job: RenderJob) -> dict[str, Any]:
    """The dict shape published on ``render_job_changed`` — one job's row.

    A plain dict rather than the row itself: ``EventBus.publish`` stores
    whatever it is given in its replay buffer, and an ORM instance would keep
    a session-bound object alive well past its transaction.
    """
    return _to_job_summary(campaign_name, job).model_dump()


def _current_run_id(session: Session) -> str:
    """Reuse the run of any non-terminal job; otherwise mint a fresh id.

    Stamped on Generate / Retry so ``queue_batch_progress`` can scope the
    header to the work the user just started, not every historical row.
    """
    active = [status.value for status in JobStatus.active()]
    existing = session.scalar(
        select(RenderJob.run_id)
        .where(RenderJob.status.in_(active), RenderJob.run_id.is_not(None))
        .limit(1)
    )
    if existing is not None:
        return existing
    return new_id()


def _run_id_for_batch(session: Session) -> str | None:
    """Which run the batch header should describe right now.

    Prefer an in-flight run; when the queue is idle, fall back to the most
    recently created run so the completion summary / Retry-failed strip still
    describes the batch that just finished.
    """
    active = [status.value for status in JobStatus.active()]
    in_flight = session.scalar(
        select(RenderJob.run_id)
        .where(RenderJob.status.in_(active), RenderJob.run_id.is_not(None))
        .limit(1)
    )
    if in_flight is not None:
        return in_flight
    return session.scalar(
        select(RenderJob.run_id)
        .where(RenderJob.run_id.is_not(None))
        .order_by(RenderJob.created_at.desc(), RenderJob.queue_position.desc())
        .limit(1)
    )


def queue_batch_progress(session: Session) -> BatchProgress:
    """Ticket 18: roll the *current run* into batch progress + ETA."""
    run_id = _run_id_for_batch(session)
    if run_id is None:
        jobs = session.scalars(select(RenderJob)).all()
    else:
        jobs = session.scalars(select(RenderJob).where(RenderJob.run_id == run_id)).all()
    return compute_batch_progress(jobs)


def batch_event_payload(session: Session) -> dict[str, Any]:
    """Dict shape for ``batch_progress_changed`` — see ``job_event_payload``."""
    return queue_batch_progress(session).model_dump()


def _alpha_cache_is_warm(workspace: WorkspaceLayout, campaign: Campaign) -> bool:
    """Whether ``campaign``'s alpha clip can be reused without an alpha_prepare job.

    Deliberately simple: ``_invalidate_alpha_cache`` already clears both
    columns on every mutation that would change the clip's content (overlay
    edit, talking-head assign/relocate, trim/focal change), so a non-null key
    whose file still exists on disk is trustworthy without recomputing it.
    """
    if not campaign.alpha_cache_key or not campaign.alpha_cache_path:
        return False
    return (workspace.root / campaign.alpha_cache_path).is_file()


def _current_alpha_key(campaign: Campaign, talking_head: MediaAsset) -> str | None:
    """Content hash for the campaign's current overlay / trim / focal state.

    Same key ``alpha_prepare`` persists on the campaign and stamps onto each
    recording's ``last_rendered_cache_key``. Returns ``None`` when the talking
    head cannot be fingerprinted (missing source) — callers treat that as
    "nothing is current".
    """
    if (
        talking_head.trim_start_ms is None
        or talking_head.trim_end_ms is None
        or talking_head.focal_x is None
        or talking_head.focal_y is None
    ):
        return None
    try:
        overlay = upgrade_overlay_config(
            json.loads(campaign.overlay_config),
            from_version=campaign.overlay_schema_version,
        )
        head = TalkingHeadConfig(
            source_path=Path(talking_head.source_path),
            trim_start_ms=talking_head.trim_start_ms,
            trim_end_ms=talking_head.trim_end_ms,
            focal_x=talking_head.focal_x,
            focal_y=talking_head.focal_y,
        )
        return alpha_cache_key(head, overlay, assets_cache_key(overlay))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _candidate_recordings_for_generate(recordings: list[MediaAsset]) -> list[MediaAsset]:
    """DB.md §6: probed OK with the source file present — the generate universe."""
    return [
        recording
        for recording in recordings
        if recording.probe_status == ProbeStatus.OK.value and not recording.file_missing
    ]


def _recording_is_current(recording: MediaAsset, current_key: str | None) -> bool:
    """Ticket 17: completed under the *current* cache key, not merely ever rendered.

    ``last_rendered_at`` lives on the recording so skip-completed survives an
    export that deleted the job row; the cache key catches overlay/trim/focal
    drift since that stamp.
    """
    if recording.last_rendered_at is None or current_key is None:
        return False
    return recording.last_rendered_cache_key == current_key


def _queued_recording_ids(session: Session, campaign_id: str) -> set[str]:
    """Asset ids that already have a non-terminal ``video_render`` job."""
    active = [status.value for status in JobStatus.active()]
    rows = session.scalars(
        select(RenderJob.asset_id).where(
            RenderJob.campaign_id == campaign_id,
            RenderJob.job_type == JobType.VIDEO_RENDER.value,
            RenderJob.status.in_(active),
            RenderJob.asset_id.is_not(None),
        )
    ).all()
    return {asset_id for asset_id in rows if asset_id is not None}


def _partition_recordings_for_generate(
    session: Session,
    campaign_id: str,
    recordings: list[MediaAsset],
    current_key: str | None,
    *,
    force: bool,
) -> tuple[list[MediaAsset], list[MediaAsset], list[MediaAsset]]:
    """Split candidates into (to_render, to_skip, already_queued).

    ``force`` (Re-render All) ignores ``last_rendered_*`` stamps but still
    respects in-flight jobs — a second click must not double-enqueue.
    """
    candidates = _candidate_recordings_for_generate(recordings)
    queued_ids = _queued_recording_ids(session, campaign_id)
    to_render: list[MediaAsset] = []
    to_skip: list[MediaAsset] = []
    already_queued: list[MediaAsset] = []
    for recording in candidates:
        if recording.id in queued_ids:
            already_queued.append(recording)
        elif not force and _recording_is_current(recording, current_key):
            to_skip.append(recording)
        else:
            to_render.append(recording)
    return to_render, to_skip, already_queued


def get_generate_plan(
    session: Session,
    workspace: WorkspaceLayout,
    campaign_id: str,
) -> GeneratePlanResponse:
    """Ticket 17: counts the UI shows before enqueueing."""
    campaign = _require_campaign(session, campaign_id)
    talking_head = _get_talking_head(session, campaign_id)
    recordings = _list_recordings(session, campaign_id)
    validation = validate_campaign(talking_head=talking_head, recordings=recordings)

    if not validation.can_generate:
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            validation.generate_blocked_reason or "This campaign cannot be generated yet.",
            status_code=422,
        )

    assert talking_head is not None  # can_generate guarantees a talking head
    current_key = _current_alpha_key(campaign, talking_head)
    to_render, to_skip, already_queued = _partition_recordings_for_generate(
        session, campaign_id, recordings, current_key, force=False
    )
    return GeneratePlanResponse(
        render_count=len(to_render),
        skip_count=len(to_skip),
        already_queued_count=len(already_queued),
        total_eligible=len(to_render) + len(to_skip) + len(already_queued),
        alpha_cache_warm=_alpha_cache_is_warm(workspace, campaign),
        all_current=len(to_render) == 0 and len(already_queued) == 0 and len(to_skip) > 0,
    )


def generate_videos(
    session: Session,
    workspace: WorkspaceLayout,
    campaign_id: str,
    *,
    force: bool = False,
    worker_pool: WorkerPool[str, Session] | None = None,
    event_bus: EventBus | None = None,
) -> GenerateVideosResponse:
    """Ticket 15/17: the *Generate Videos* / *Re-render All* actions.

    Enqueues one ``alpha_prepare`` job (only when the cache is cold) and one
    ``video_render`` job per recording that still needs rendering, then returns
    immediately — the worker pool does the actual work. When every recording is
    already current and ``force`` is false, returns an empty batch with
    ``all_current=True`` rather than enqueueing nothing silently or erroring.

    ``worker_pool`` / ``event_bus`` are optional so the function stays testable
    without a running pool or SSE bus; the router always passes the real ones.
    """
    campaign = _require_campaign(session, campaign_id)
    talking_head = _get_talking_head(session, campaign_id)
    recordings = _list_recordings(session, campaign_id)
    validation = validate_campaign(talking_head=talking_head, recordings=recordings)

    if not validation.can_generate:
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            validation.generate_blocked_reason or "This campaign cannot be generated yet.",
            status_code=422,
        )

    assert talking_head is not None
    current_key = _current_alpha_key(campaign, talking_head)
    to_render, to_skip, already_queued = _partition_recordings_for_generate(
        session, campaign_id, recordings, current_key, force=force
    )

    if not to_render:
        # Everything current, already queued, or no candidates. Report clearly.
        return GenerateVideosResponse(
            enqueued_job_count=0,
            render_count=0,
            skip_count=len(to_skip),
            already_queued_count=len(already_queued),
            alpha_cache_warm=_alpha_cache_is_warm(workspace, campaign),
            all_current=len(to_skip) > 0 and len(already_queued) == 0,
            jobs=[],
        )

    alpha_cache_warm = _alpha_cache_is_warm(workspace, campaign)
    run_id = _current_run_id(session)
    active_statuses = [status.value for status in JobStatus.active()]

    next_position = int(session.scalar(select(func.max(RenderJob.queue_position))) or 0) + 1

    created: list[RenderJob] = []
    alpha_job: RenderJob | None = None
    if not alpha_cache_warm:
        # Reuse an in-flight alpha for this campaign rather than enqueueing a
        # second prepare that would race and leave videos pointing at the wrong
        # dependency.
        alpha_job = session.scalar(
            select(RenderJob)
            .where(
                RenderJob.campaign_id == campaign_id,
                RenderJob.job_type == JobType.ALPHA_PREPARE.value,
                RenderJob.status.in_(active_statuses),
            )
            .order_by(RenderJob.queue_position, RenderJob.id)
            .limit(1)
        )
        if alpha_job is None:
            alpha_job = RenderJob(
                campaign_id=campaign_id,
                job_type=JobType.ALPHA_PREPARE.value,
                status=JobStatus.WAITING.value,
                queue_position=next_position,
                run_id=run_id,
            )
            session.add(alpha_job)
            session.flush()
            created.append(alpha_job)
            next_position += 1

    for recording in to_render:
        job = RenderJob(
            campaign_id=campaign_id,
            asset_id=recording.id,
            job_type=JobType.VIDEO_RENDER.value,
            status=JobStatus.WAITING.value,
            queue_position=next_position,
            depends_on_job_id=alpha_job.id if alpha_job is not None else None,
            output_filename=f"{recording.output_basename}.mp4",
            run_id=run_id,
        )
        session.add(job)
        created.append(job)
        next_position += 1

    campaign.updated_at = utcnow_iso()
    session.commit()
    for job in created:
        session.refresh(job)

    if event_bus is not None:
        for job in created:
            event_bus.render_job_changed(job_event_payload(campaign.name, job))
        # Ticket 18: sidebar badge updates as soon as jobs land, from any screen.
        event_bus.batch_progress_changed(batch_event_payload(session))

    if worker_pool is not None:
        worker_pool.wake()

    return GenerateVideosResponse(
        enqueued_job_count=len(created),
        render_count=len(to_render),
        skip_count=len(to_skip),
        already_queued_count=len(already_queued),
        alpha_cache_warm=alpha_cache_warm,
        all_current=False,
        jobs=[_to_job_summary(campaign.name, job) for job in created],
    )


def list_render_queue(
    session: Session,
    *,
    worker_pool: WorkerPool[str, Session] | None = None,
) -> RenderQueueResponse:
    """Ticket 15/18/22: global queue rows, batch rollup, and pause/recovery flags."""
    rows = session.execute(
        select(RenderJob, Campaign.name)
        .join(Campaign, Campaign.id == RenderJob.campaign_id)
        .order_by(RenderJob.queue_position, RenderJob.id)
    ).all()
    jobs = [_to_job_summary(name, job) for job, name in rows]
    return RenderQueueResponse(
        jobs=jobs,
        batch=queue_batch_progress(session),
        paused=bool(worker_pool is not None and worker_pool.paused),
        show_resume_prompt=bool(worker_pool is not None and worker_pool.show_resume_prompt),
    )


def pause_render_queue(
    session: Session,
    *,
    worker_pool: WorkerPool[str, Session] | None = None,
) -> RenderQueueResponse:
    """Ticket 19: stop claiming the next job; the in-flight job finishes."""
    if worker_pool is not None:
        worker_pool.pause(show_resume_prompt=False)
    return list_render_queue(session, worker_pool=worker_pool)


def resume_render_queue(
    session: Session,
    *,
    worker_pool: WorkerPool[str, Session] | None = None,
) -> RenderQueueResponse:
    """Ticket 19/22: clear a recovery (or user) pause and let the worker claim again."""
    if worker_pool is not None:
        worker_pool.resume()
    return list_render_queue(session, worker_pool=worker_pool)


def _cancel_dependents(
    session: Session, workspace: WorkspaceLayout, job: RenderJob
) -> list[RenderJob]:
    """Delete ``waiting`` jobs that depend on ``job`` (ticket 19).

    Modelled on ``_cascade_fail_dependents``: only waiting dependents — a row
    already claimed is left for its own worker. Called *before* the target row
    is deleted so the campaign cannot stay locked by orphaned waiters.
    """
    dependents = list(
        session.scalars(
            select(RenderJob).where(
                RenderJob.depends_on_job_id == job.id,
                RenderJob.status == JobStatus.WAITING.value,
            )
        ).all()
    )
    for dependent in dependents:
        _delete_job_partials(workspace, dependent)
        session.delete(dependent)
    return dependents


def cancel_render_job(
    session: Session,
    workspace: WorkspaceLayout,
    event_bus: EventBus,
    job_id: str,
    *,
    worker_pool: WorkerPool[str, Session] | None = None,
) -> RenderQueueResponse:
    """Ticket 19: cancel one queued or active job.

    A running job has its FFmpeg process killed and its partial output deleted.
    Waiting dependents of an ``alpha_prepare`` are cancelled with it. The rows
    are removed so they cannot keep the campaign locked.
    """
    job = session.get(RenderJob, job_id)
    if job is None:
        raise ApiError(ApiErrorCode.NOT_FOUND, "Render job not found.", status_code=404)

    if job.status in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "Only queued or active jobs can be cancelled.",
            status_code=422,
        )

    campaign_id = job.campaign_id
    if job.status in {status.value for status in JobStatus.interrupted()}:
        request_cancel(job.id)
    _cancel_dependents(session, workspace, job)
    _delete_job_partials(workspace, job)
    session.delete(job)
    session.commit()

    if not is_campaign_locked(session, campaign_id):
        event_bus.campaign_lock_changed(campaign_id, locked=False)
    event_bus.batch_progress_changed(batch_event_payload(session))
    return list_render_queue(session, worker_pool=worker_pool)


def _reset_job_to_waiting(job: RenderJob) -> None:
    """Clear progress/error/output fields and return a job to ``waiting``."""
    job.status = JobStatus.WAITING.value
    job.progress_pct = 0.0
    job.error_message = None
    job.error_details = None
    job.ffmpeg_command = None
    job.started_at = None
    job.finished_at = None
    job.output_path = None


def retry_render_job(
    session: Session,
    workspace: WorkspaceLayout,
    event_bus: EventBus,
    job_id: str,
    *,
    worker_pool: WorkerPool[str, Session] | None = None,
) -> RenderQueueResponse:
    """Ticket 19: re-run a single failed job with a clean waiting state.

    When the job depends on a still-``failed`` alpha, that dependency is reset
    too — otherwise Retry would park the video on an unclaimable wait forever.
    """
    job = session.get(RenderJob, job_id)
    if job is None:
        raise ApiError(ApiErrorCode.NOT_FOUND, "Render job not found.", status_code=404)
    if job.status != JobStatus.FAILED.value:
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "Only failed jobs can be retried.",
            status_code=422,
        )

    campaign = session.get(Campaign, job.campaign_id)
    campaign_name = campaign.name if campaign is not None else ""
    run_id = _current_run_id(session)
    reset_jobs = [job]

    _delete_job_partials(workspace, job)
    _reset_job_to_waiting(job)
    job.run_id = run_id

    if job.depends_on_job_id is not None:
        dependency = session.get(RenderJob, job.depends_on_job_id)
        if dependency is not None and dependency.status == JobStatus.FAILED.value:
            _delete_job_partials(workspace, dependency)
            _reset_job_to_waiting(dependency)
            dependency.run_id = run_id
            reset_jobs.append(dependency)

    session.commit()
    for reset in reset_jobs:
        session.refresh(reset)
        event_bus.render_job_changed(job_event_payload(campaign_name, reset))
    event_bus.batch_progress_changed(batch_event_payload(session))
    if campaign is not None and is_campaign_locked(session, campaign.id):
        event_bus.campaign_lock_changed(campaign.id, locked=True)

    if worker_pool is not None:
        if worker_pool.paused:
            worker_pool.resume()
        else:
            worker_pool.wake()

    return list_render_queue(session, worker_pool=worker_pool)


def reorder_render_queue(
    session: Session,
    event_bus: EventBus,
    job_ids: list[str],
    *,
    worker_pool: WorkerPool[str, Session] | None = None,
) -> RenderQueueResponse:
    """Ticket 19: persist a new global order; the worker reads ``queue_position``.

    The actively-encoding (or otherwise in-flight) job stays pinned at its
    index. ``alpha_prepare`` rows stay above their campaign's video jobs
    (DB.md §3.3).
    """
    jobs = list(session.scalars(select(RenderJob)).all())
    by_id = {job.id: job for job in jobs}
    if not jobs:
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "There are no jobs to reorder.",
            status_code=422,
        )
    if len(job_ids) != len(by_id) or set(job_ids) != set(by_id):
        raise ApiError(
            ApiErrorCode.VALIDATION_ERROR,
            "job_ids must list every render job exactly once.",
            status_code=422,
        )

    current_order = sorted(jobs, key=lambda job: (job.queue_position, job.id))
    pinned = {status.value for status in JobStatus.interrupted()}
    for index, current in enumerate(current_order):
        if current.status in pinned and job_ids[index] != current.id:
            raise ApiError(
                ApiErrorCode.VALIDATION_ERROR,
                "The actively encoding job is pinned and cannot be moved or displaced.",
                status_code=422,
            )

    for campaign_id in {job.campaign_id for job in jobs}:
        seen_video = False
        for job_id in job_ids:
            job = by_id[job_id]
            if job.campaign_id != campaign_id:
                continue
            if job.job_type == JobType.VIDEO_RENDER.value:
                seen_video = True
            elif job.job_type == JobType.ALPHA_PREPARE.value and seen_video:
                raise ApiError(
                    ApiErrorCode.VALIDATION_ERROR,
                    "Prepare-overlay jobs stay pinned above their campaign's videos.",
                    status_code=422,
                )

    for position, job_id in enumerate(job_ids, start=1):
        by_id[job_id].queue_position = position
    session.commit()
    event_bus.batch_progress_changed(batch_event_payload(session))
    return list_render_queue(session, worker_pool=worker_pool)


def retry_failed_jobs(
    session: Session,
    workspace: WorkspaceLayout,
    event_bus: EventBus,
    *,
    worker_pool: WorkerPool[str, Session] | None = None,
) -> RetryFailedResponse:
    """Ticket 20: re-enqueue every failed job; leave completed rows alone.

    Resets status to ``waiting``, clears error fields and any partial output,
    and wakes the worker. Dependencies are preserved — a cascaded video job
    that points at a failed ``alpha_prepare`` waits for that alpha job again
    after both are reset. Jobs receive a fresh ``run_id`` so the batch header
    describes this retry, not the drained prior run.
    """
    failed = session.scalars(
        select(RenderJob)
        .where(RenderJob.status == JobStatus.FAILED.value)
        .order_by(RenderJob.queue_position, RenderJob.id)
    ).all()
    if not failed:
        return RetryFailedResponse(retried_job_count=0, jobs=[])

    campaign_ids = {job.campaign_id for job in failed}
    names = {
        campaign_id: name
        for campaign_id, name in session.execute(
            select(Campaign.id, Campaign.name).where(Campaign.id.in_(campaign_ids))
        ).all()
    }

    run_id = _current_run_id(session)
    for job in failed:
        _delete_job_partials(workspace, job)
        _reset_job_to_waiting(job)
        job.run_id = run_id

    session.commit()
    for job in failed:
        session.refresh(job)

    summaries = [_to_job_summary(names.get(job.campaign_id, ""), job) for job in failed]
    for summary in summaries:
        event_bus.render_job_changed(summary.model_dump())
    event_bus.batch_progress_changed(batch_event_payload(session))

    if worker_pool is not None:
        # A recovery pause would otherwise leave retried jobs sitting idle.
        if worker_pool.paused:
            worker_pool.resume()
        else:
            worker_pool.wake()

    return RetryFailedResponse(retried_job_count=len(summaries), jobs=summaries)


def _delete_job_partials(workspace: WorkspaceLayout, job: RenderJob) -> None:
    """Remove encode fragments for ``job`` without touching a prior good final.

    Deletes ``job.output_path`` when set (this job's own committed output) and
    any ``{output_filename}.*.part.mp4`` siblings. Does **not** unlink
    ``outputs/<campaign>/<output_filename>`` by name inference: for a
    ``waiting`` / ``failed`` retry that path is usually the completed MP4 from
    an earlier batch, and destroying it strands ``last_rendered_*`` stamps
    (ticket 17) pointing at a missing file.

    A crash between the atomic ``part_path.replace()`` and the status commit
    can leave a complete, valid MP4 at the final path with no ``output_path``
    yet. Leaving it is harmless — the recording is still un-current, the next
    Generate re-renders, and ``part_path.replace()`` overwrites atomically.
    """
    if job.output_path:
        _safe_unlink(workspace, workspace.root / job.output_path)

    if job.job_type != JobType.VIDEO_RENDER.value or not job.output_filename:
        return

    out_dir = workspace.outputs / job.campaign_id
    if not out_dir.is_dir():
        return
    for path in out_dir.glob(f"{job.output_filename}.*.part.mp4"):
        _safe_unlink(workspace, path)


def reset_interrupted_jobs(session: Session, workspace: WorkspaceLayout) -> int:
    """Ticket 22: reset in-flight jobs at boot and scrub their partial outputs.

    DB.md §3.3: a job left ``preparing``/``rendering``/``encoding`` when the
    process died did not fail, it just never finished — reset to ``waiting``
    so it is retried, and delete whatever ``.part.mp4`` it left behind.
    Pre-existing final outputs are left intact. The caller pauses the worker
    pool with a Resume prompt when this returns a non-zero count.
    """
    interrupted = [status.value for status in JobStatus.interrupted()]
    jobs = session.scalars(select(RenderJob).where(RenderJob.status.in_(interrupted))).all()
    if not jobs:
        return 0

    for job in jobs:
        _delete_job_partials(workspace, job)
        _reset_job_to_waiting(job)

    session.commit()
    return len(jobs)
