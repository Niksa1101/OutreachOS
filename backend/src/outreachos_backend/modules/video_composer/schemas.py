"""Video Composer API models — the OpenAPI surface for campaign CRUD."""

from enum import StrEnum

from pydantic import BaseModel, Field

from outreachos_backend.rendering.config import OverlayConfig


class CampaignStatus(StrEnum):
    """Backend-computed campaign status.

    Ticket 01 starts thin: draft-like or has rendered before. Ticket 07 extends
    this with validation state; ticket 15 adds queue activity. The UI renders
    whatever value the backend sends.
    """

    DRAFT = "draft"
    READY = "ready"
    BLOCKED = "blocked"
    HAS_RENDERED = "has_rendered"


class ValidationIssue(BaseModel):
    code: str = Field(description="DB.md §4.3 issue code.")
    severity: str = Field(description="``blocking`` or ``warning``.")
    message: str = Field(description="Plain-language explanation for the UI.")
    asset_id: str | None = Field(
        default=None,
        description="Media asset row this issue applies to, when row-scoped.",
    )


class CampaignValidation(BaseModel):
    issues: list[ValidationIssue] = Field(
        default_factory=list,
        description="All validation findings, computed on demand and never persisted.",
    )
    can_generate: bool = Field(
        description="False when campaign-level blockers leave nothing to enqueue."
    )
    generate_blocked_reason: str | None = Field(
        default=None,
        description="Specific reason Generate is disabled, when ``can_generate`` is false.",
    )
    renderable_recording_count: int = Field(
        description="Recordings that would be enqueued on Generate."
    )
    warning_count: int = Field(description="Number of warning-severity issues.")


class CampaignSummary(BaseModel):
    id: str
    name: str
    recording_count: int = Field(description="Number of screen recordings in the campaign.")
    last_rendered_at: str | None = Field(
        description="ISO-8601 UTC of the most recent successful render, if any."
    )
    status: CampaignStatus


class TalkingHeadDetail(BaseModel):
    id: str
    source_path: str = Field(description="Absolute path to the source file on disk.")
    source_filename: str
    file_missing: bool = Field(
        description="True when the source file is absent at ``source_path``."
    )
    duration_ms: int
    width: int = Field(description="Display width after rotation, in pixels.")
    height: int = Field(description="Display height after rotation, in pixels.")
    fps: float
    video_codec: str
    has_audio: bool
    trim_start_ms: int
    trim_end_ms: int
    focal_x: float
    focal_y: float


class RecordingDetail(BaseModel):
    id: str
    source_path: str = Field(description="Absolute path to the source file on disk.")
    source_filename: str
    file_missing: bool = Field(
        description="True when the source file is absent at ``source_path``."
    )
    company_name: str
    output_basename: str = Field(
        description="Resolved output filename stem at add time, including any (2) suffix."
    )
    probe_status: str
    probe_error: str | None = None
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    video_codec: str | None = None
    has_audio: bool | None = None
    sort_order: int


class CampaignDetail(CampaignSummary):
    overlay_config: str = Field(description="Overlay JSON, DB.md §4.1.")
    overlay_schema_version: int
    talking_head: TalkingHeadDetail | None = None
    recordings: list[RecordingDetail] = Field(
        default_factory=list,
        description="Screen recordings in sort order.",
    )
    validation: CampaignValidation
    is_locked: bool = Field(
        description=(
            "True while this campaign has any queued or active render job "
            "(DB.md §6's editor lock check). Overlay config, talking-head "
            "trim/focal point, and preset application are read-only while locked."
        )
    )
    lock_reason: str | None = Field(
        default=None,
        description="Plain-language explanation, set whenever is_locked is true.",
    )
    created_at: str
    updated_at: str


class CampaignListResponse(BaseModel):
    campaigns: list[CampaignSummary]


class CampaignCreateRequest(BaseModel):
    name: str | None = Field(
        default=None,
        max_length=200,
        description="Defaults to 'Untitled campaign' when omitted.",
    )


class CampaignUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TalkingHeadAssignRequest(BaseModel):
    source_path: str = Field(
        min_length=1,
        description="Absolute path to a video file on disk. The file is probed but never copied.",
    )


class TalkingHeadTrimRequest(BaseModel):
    trim_start_ms: int = Field(ge=0, description="Trim in-point, milliseconds from source start.")
    trim_end_ms: int = Field(gt=0, description="Trim out-point, milliseconds from source start.")
    focal_x: float = Field(ge=0.0, le=1.0, description="Normalized crop center, DB.md §4.1.")
    focal_y: float = Field(ge=0.0, le=1.0, description="Normalized crop center, DB.md §4.1.")


class AssetRelocateRequest(BaseModel):
    source_path: str = Field(
        min_length=1,
        description="Absolute path to the relocated video file on disk.",
    )


class RecordingImportRejected(BaseModel):
    source_path: str
    message: str = Field(description="Plain-language reason this file was not imported.")


class RecordingUpdateRequest(BaseModel):
    company_name: str = Field(max_length=200)


class RecordingImportRequest(BaseModel):
    source_paths: list[str] = Field(
        min_length=1,
        description="Absolute paths to video files on disk. Each file is probed but never copied.",
    )


class RecordingImportResponse(BaseModel):
    added: list[RecordingDetail]
    rejected: list[RecordingImportRejected] = Field(
        description="Files rejected before probing, such as duplicate paths or missing files."
    )
    failed: list[RecordingImportRejected] = Field(
        description="Files that were added but could not be probed as video."
    )
    recording_count: int = Field(
        description="Total screen recordings in the campaign after import."
    )


class CampaignDeleteAlphaClip(BaseModel):
    present: bool = Field(description="Whether a cached alpha clip file exists on disk.")
    size_bytes: int | None = Field(
        default=None,
        description="File size in bytes when ``present`` is true.",
    )


class CampaignDeleteOutputs(BaseModel):
    count: int = Field(description="Number of un-exported output files in workspace staging.")
    total_size_bytes: int = Field(description="Combined size of staged output files in bytes.")


class PreviewFrameResponse(BaseModel):
    available: bool = Field(description="True when ``frame_path`` points at a usable cached frame.")
    frame_path: str | None = Field(
        default=None,
        description="Absolute path to the cached JPEG frame, when available.",
    )
    error: str | None = Field(
        default=None,
        description=(
            "Plain-language extraction failure reason. Only set when a first "
            "recording exists but the frame could not be produced — absent "
            "(not an error) when the campaign simply has no recordings yet."
        ),
    )


class CampaignDeletePreview(BaseModel):
    campaign_id: str
    campaign_name: str
    asset_count: int = Field(description="Media asset rows that will be removed with the campaign.")
    recording_count: int
    talking_head_count: int = Field(description="0 or 1.")
    alpha_clip: CampaignDeleteAlphaClip
    outputs: CampaignDeleteOutputs


class OverlayPresetSummary(BaseModel):
    id: str
    name: str
    overlay_schema_version: int
    created_at: str
    updated_at: str


class OverlayPresetDetail(OverlayPresetSummary):
    overlay_config: str = Field(description="Overlay JSON, DB.md §4.1.")


class OverlayPresetListResponse(BaseModel):
    presets: list[OverlayPresetSummary]


class OverlayPresetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    overlay: OverlayConfig


class OverlayPresetRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ApplyPresetRequest(BaseModel):
    preset_id: str = Field(min_length=1)


class RenderJobSummary(BaseModel):
    """One row of the global Render Queue (ticket 15)."""

    id: str
    campaign_id: str
    campaign_name: str
    asset_id: str | None = None
    job_type: str
    status: str
    queue_position: int
    progress_pct: float
    depends_on_job_id: str | None = None
    output_filename: str | None = None
    error_message: str | None = Field(
        default=None, description="Plain-language summary, set only when status is failed."
    )
    error_details: str | None = Field(
        default=None,
        description=(
            "Technical detail for a failed job — typically FFmpeg stderr, "
            "capped per ADR-0011. Shown behind an expandable UI, not by default."
        ),
    )
    ffmpeg_command: str | None = Field(
        default=None,
        description="Exact FFmpeg argv as a pasteable shell command, when one ran.",
    )
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class RetryFailedResponse(BaseModel):
    """Ticket 20: result of re-enqueueing every currently failed job."""

    retried_job_count: int = Field(description="Failed jobs reset to waiting by this call.")
    jobs: list[RenderJobSummary]


class BatchProgress(BaseModel):
    """Queue-wide rollup for the Render Queue header and sidebar badge (ticket 18)."""

    total: int = Field(description="Every job currently in the queue, all campaigns.")
    completed: int
    failed: int
    active: int = Field(description="Jobs in preparing, rendering, or encoding — work in flight.")
    waiting: int
    active_job_count: int = Field(
        description=(
            "Waiting plus in-flight. The sidebar badge; zero means the queue is idle "
            "even if completed/failed rows remain."
        )
    )
    progress_pct: float = Field(
        description=(
            "Fractional batch progress 0-100, counting completed/failed jobs fully "
            "and in-flight jobs by their per-job percentage."
        )
    )
    eta_seconds: int | None = Field(
        default=None,
        description=(
            "Estimated seconds remaining from measured video-render throughput. "
            "Null when fewer than two video renders have finished — the UI shows "
            "a calm placeholder rather than a wild number."
        ),
    )


class RenderQueueResponse(BaseModel):
    jobs: list[RenderJobSummary]
    batch: BatchProgress
    paused: bool = Field(
        default=False,
        description="True while the worker pool is not claiming new jobs.",
    )
    show_resume_prompt: bool = Field(
        default=False,
        description=(
            "True after crash/close recovery paused the queue (ticket 22). "
            "The UI shows a Resume prompt until the user resumes."
        ),
    )


class ReorderRenderQueueRequest(BaseModel):
    """Ticket 19: full new order for every job currently in the queue."""

    job_ids: list[str] = Field(
        min_length=1,
        description="Every render-job id exactly once, in the desired queue order.",
    )


class GeneratePlanResponse(BaseModel):
    """Ticket 17: what Generate / Re-render All would do, before enqueueing."""

    render_count: int = Field(description="Recordings that would be enqueued by a normal Generate.")
    skip_count: int = Field(
        description=(
            "Recordings already current under the campaign's present overlay/"
            "trim/focal cache key — skipped by Generate, included by Re-render All."
        )
    )
    already_queued_count: int = Field(
        description=(
            "Eligible recordings that already have a non-terminal video_render job — "
            "neither rendered nor skipped; a second Generate must not re-enqueue them."
        )
    )
    total_eligible: int = Field(
        description=(
            "Probed-OK, present screen recordings "
            "(render_count + skip_count + already_queued_count)."
        )
    )
    alpha_cache_warm: bool = Field(
        description=(
            "True when the campaign's alpha clip can be reused without an alpha_prepare job."
        )
    )
    all_current: bool = Field(
        description=(
            "True when every eligible recording is already current — "
            "Generate would enqueue nothing."
        )
    )


class GenerateVideosRequest(BaseModel):
    force: bool = Field(
        default=False,
        description=(
            "Re-render All: enqueue every eligible recording regardless of "
            "last-rendered state. When false, skip recordings whose "
            "last_rendered_cache_key still matches the current campaign cache key."
        ),
    )


class GenerateVideosResponse(BaseModel):
    enqueued_job_count: int = Field(
        description="Jobs created by this call: one alpha_prepare (if the cache "
        "is cold) plus one video_render per recording that will render."
    )
    render_count: int = Field(
        description="Number of video_render jobs enqueued (excludes alpha_prepare)."
    )
    skip_count: int = Field(
        description=(
            "Eligible recordings left un-enqueued because they are already "
            "current. Zero when ``force`` is true."
        )
    )
    already_queued_count: int = Field(
        description=(
            "Eligible recordings left un-enqueued because they already have a "
            "non-terminal video_render job in the queue."
        )
    )
    alpha_cache_warm: bool = Field(
        description=(
            "True when the campaign's alpha clip was reused from cache and no "
            "alpha_prepare row was enqueued — encoding starts immediately."
        )
    )
    all_current: bool = Field(
        description=(
            "True when nothing was enqueued because every eligible recording "
            "is already current and ``force`` was false."
        )
    )
    jobs: list[RenderJobSummary]
