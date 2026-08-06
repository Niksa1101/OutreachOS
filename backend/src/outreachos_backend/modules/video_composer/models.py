"""Video Composer's tables — DB.md §3.1 through §3.4.

Q16 lands the **entire** schema in P0 rather than growing it per phase. P1's
CLI and P2 both need it, and DB.md §7's "the database is a user document, it is
never wiped to resolve a schema problem" makes a real baseline worth having
before there is any data to migrate.

DB.md §7's forward-compatibility note applies here: future modules add their own
tables namespaced by module prefix. No table below is designed to be reshaped to
accommodate them.
"""

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from outreachos_backend.core.enums import AssetRole, JobStatus, JobType, ProbeStatus
from outreachos_backend.core.models import Base, TimestampMixin, new_id

__all__ = ["Campaign", "MediaAsset", "OverlayPreset", "RenderJob"]


def _check_in(
    column: str, values: type[AssetRole] | type[JobStatus] | type[JobType] | type[ProbeStatus]
) -> str:
    """Render an ``IN`` list from an enum.

    Safe *here* because the models are the live definition. The migrations are
    the opposite case — Q59 requires them to hardcode the literals, because a
    migration that imported this would have its meaning rewritten by a later
    enum change.
    """
    literals = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({literals})"


class Campaign(TimestampMixin, Base):
    """DB.md §3.1."""

    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "quality_override IS NULL OR quality_override IN ('draft', 'standard', 'high')",
            name="ck_campaigns_quality_override",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    overlay_config: Mapped[str] = mapped_column(Text, nullable=False)
    """JSON, DB.md §4.1.

    A column rather than a table because it is strictly 1:1 with a campaign, is
    never queried by field, and must absorb new properties without a migration.
    """

    overlay_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    """Mirrors the JSON field so it *is* queryable — which is what makes the
    in-code upgrader in DB.md §4.1 able to find rows that need it."""

    quality_override: Mapped[str | None] = mapped_column(String, nullable=True)
    """NULL = use the global default from ``app_settings``."""

    alpha_cache_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    """DB.md §5. Any change to the talking head, its trim, its focal point, or
    the overlay config invalidates this and forces a rebuild."""

    alpha_cache_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Relative to the workspace, so moving the workspace does not break it."""

    default_export_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    assets: Mapped[list["MediaAsset"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MediaAsset(TimestampMixin, Base):
    """DB.md §3.2. One row per file referenced by a campaign.

    **Source files are never copied or modified.** ``source_path`` is an
    absolute path to where the user's file actually lives.
    """

    __tablename__ = "media_assets"
    __table_args__ = (
        # DB.md §3.2: the same file cannot be added to a campaign twice.
        UniqueConstraint("campaign_id", "source_path", name="uq_media_assets_campaign_source"),
        CheckConstraint(_check_in("role", AssetRole), name="ck_media_assets_role"),
        CheckConstraint(
            _check_in("probe_status", ProbeStatus), name="ck_media_assets_probe_status"
        ),
        CheckConstraint("file_missing IN (0, 1)", name="ck_media_assets_file_missing"),
        CheckConstraint("name_auto_suffixed IN (0, 1)", name="ck_media_assets_name_auto_suffixed"),
        CheckConstraint(
            "has_audio IS NULL OR has_audio IN (0, 1)",
            name="ck_media_assets_has_audio",
        ),
        # DB.md §4.1: normalised crop centre.
        CheckConstraint(
            "focal_x IS NULL OR (focal_x >= 0.0 AND focal_x <= 1.0)",
            name="ck_media_assets_focal_x",
        ),
        CheckConstraint(
            "focal_y IS NULL OR (focal_y >= 0.0 AND focal_y <= 1.0)",
            name="ck_media_assets_focal_y",
        ),
        Index("ix_media_assets_campaign_role_order", "campaign_id", "role", "sort_order"),
        # DB.md §3.2: at most one talking head per campaign.
        #
        # A *partial* unique index, because the rule applies to one role only.
        # A plain unique constraint on (campaign_id, role) would also forbid a
        # second screen recording, which is the normal case — a campaign is a
        # batch of them.
        Index(
            "uq_media_assets_one_talking_head",
            "campaign_id",
            unique=True,
            sqlite_where=text(f"role = '{AssetRole.TALKING_HEAD.value}'"),
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(
        Text, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[str] = mapped_column(String, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_filename: Mapped[str] = mapped_column(Text, nullable=False)
    """For display and for relocation matching when a source file moves."""

    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    """``screen_recording`` only."""

    output_basename: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Resolved **at add time**, including any ``(2)`` suffix — so two
    recordings for the same company get stable, distinct names rather than
    racing at render time."""

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- probe results ---
    probe_status: Mapped[str] = mapped_column(
        String, nullable=False, default=ProbeStatus.PENDING.value
    )
    probe_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """DB.md §2: integer milliseconds. Never floats, never seconds."""
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    video_codec: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_audio: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- link health ---
    file_missing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_verified_at: Mapped[str | None] = mapped_column(Text, nullable=True)

    name_auto_suffixed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """``screen_recording`` only — set when ``resolve_unique_company_name`` adds a suffix."""

    # --- talking head only ---
    trim_start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trim_end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    focal_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    focal_y: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- render tracking ---
    last_rendered_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    """DB.md §6: drives skip-completed. It lives here rather than on
    ``render_jobs`` because completed jobs are deleted after export — without
    it, pressing Generate after an export would re-render the whole campaign."""

    last_rendered_cache_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Detects config drift since the last successful render."""

    campaign: Mapped[Campaign] = relationship(back_populates="assets")


class RenderJob(TimestampMixin, Base):
    """DB.md §3.3. The global queue.

    One table for both job types so the queue is genuinely unified — a single
    ``queue_position`` ordering, one worker loop, one place to look.
    """

    __tablename__ = "render_jobs"
    __table_args__ = (
        CheckConstraint(_check_in("job_type", JobType), name="ck_render_jobs_job_type"),
        CheckConstraint(_check_in("status", JobStatus), name="ck_render_jobs_status"),
        CheckConstraint(
            "progress_pct >= 0 AND progress_pct <= 100",
            name="ck_render_jobs_progress_pct",
        ),
        CheckConstraint("attempts >= 0", name="ck_render_jobs_attempts"),
        Index("ix_render_jobs_status_position", "status", "queue_position"),
        Index("ix_render_jobs_campaign", "campaign_id"),
        Index("ix_render_jobs_depends_on", "depends_on_job_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(
        Text, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=True
    )
    """NULL for ``alpha_prepare`` — that job belongs to the campaign, not to
    any one recording."""

    job_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default=JobStatus.WAITING.value)
    queue_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    depends_on_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Video jobs point at their campaign's ``alpha_prepare``.

    Deliberately **not** a foreign key: DB.md §3.3 deletes completed jobs after
    export, and a self-referential FK would either block that or cascade the
    deletion into jobs that are still queued.
    """

    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Relative to the workspace."""

    output_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Snapshot of ``output_basename`` at enqueue time, so renaming the asset
    mid-queue cannot change where a running job writes."""

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Plain-language summary, for the queue row."""

    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Full FFmpeg stderr. The thing that actually explains a failure."""

    ffmpeg_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    """The exact command, so it can be pasted into a terminal unchanged —
    Tech.md §5's whole argument for constructing commands explicitly."""

    started_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[str | None] = mapped_column(Text, nullable=True)


class OverlayPreset(TimestampMixin, Base):
    """DB.md §3.4. Global across campaigns.

    Presets are **snapshots applied by copy**. There is intentionally no
    foreign key from a campaign back to a preset: editing a preset must never
    mutate a campaign that already used it.
    """

    __tablename__ = "overlay_presets"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    overlay_config: Mapped[str] = mapped_column(Text, nullable=False)
    overlay_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
