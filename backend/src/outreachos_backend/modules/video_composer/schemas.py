"""Video Composer API models — the OpenAPI surface for campaign CRUD."""

from enum import StrEnum

from pydantic import BaseModel, Field


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
