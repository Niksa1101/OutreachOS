"""Campaign CRUD — the Video Composer service layer."""

import contextlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from outreachos_backend.core.enums import AssetRole, ProbeStatus
from outreachos_backend.core.errors import ApiError, ApiErrorCode
from outreachos_backend.core.timeutil import utcnow_iso
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.modules.video_composer.filename_cleanup import (
    derive_company_name,
    resolve_unique_company_name,
)
from outreachos_backend.modules.video_composer.models import Campaign, MediaAsset
from outreachos_backend.modules.video_composer.schemas import (
    CampaignDeleteAlphaClip,
    CampaignDeleteOutputs,
    CampaignDeletePreview,
    CampaignDetail,
    CampaignStatus,
    CampaignSummary,
    CampaignValidation,
    PreviewFrameResponse,
    RecordingDetail,
    RecordingImportRejected,
    RecordingImportResponse,
    TalkingHeadDetail,
)
from outreachos_backend.modules.video_composer.validation import validate_campaign
from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.cache import (
    CacheLayout,
    alpha_clip_path,
    alpha_manifest_path,
    preview_frame_cache_key,
    preview_frame_path,
)
from outreachos_backend.rendering.config import OverlayConfig
from outreachos_backend.rendering.errors import RenderFatalError, RenderProcessError
from outreachos_backend.rendering.frame_extract import extract_frame
from outreachos_backend.rendering.probe import ProbeResult, probe_media

DEFAULT_CAMPAIGN_NAME = "Untitled campaign"

PREVIEW_FRAME_TARGET_MS = 2000
"""Ticket 09: extract at 00:02, clamped to the recording's midpoint when shorter."""


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
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(workspace.root.resolve()):
            return
        if resolved.is_file():
            resolved.unlink()
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
