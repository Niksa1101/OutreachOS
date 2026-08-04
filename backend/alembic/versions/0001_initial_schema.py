"""The entire DB.md §3 schema.

Revision ID: 0001
Revises:
Create Date: 2026-08-04

Q16 lands all five tables in P0 rather than growing them per phase: P1's CLI and
P2 both need them, and DB.md §7's "the database is a user document, it is never
wiped to resolve a schema problem" makes a real baseline worth having before
there is any data to lose.

**Every enum value below is a hardcoded literal, deliberately** (Q59). This file
does not import ``core.enums`` and must never start. A migration is a frozen
historical snapshot of what the schema was at a point in time; importing a live
enum would mean adding a member silently rewrites the meaning of a migration
that already ran, so the ``CHECK`` constraint recorded here would stop
describing the constraint this revision actually created.

``test_schema_drift.py`` is what keeps the duplication honest.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- DB.md §3.1 ---------------------------------------------------------
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("overlay_config", sa.Text(), nullable=False),
        sa.Column("overlay_schema_version", sa.Integer(), nullable=False),
        sa.Column("quality_override", sa.String(), nullable=True),
        sa.Column("alpha_cache_key", sa.Text(), nullable=True),
        sa.Column("alpha_cache_path", sa.Text(), nullable=True),
        sa.Column("default_export_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "quality_override IS NULL OR quality_override IN ('draft', 'standard', 'high')",
            name="ck_campaigns_quality_override",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- DB.md §3.2 ---------------------------------------------------------
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("campaign_id", sa.Text(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_filename", sa.Text(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("output_basename", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("probe_status", sa.String(), nullable=False),
        sa.Column("probe_error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("video_codec", sa.Text(), nullable=True),
        sa.Column("has_audio", sa.Integer(), nullable=True),
        sa.Column("file_missing", sa.Integer(), nullable=False),
        sa.Column("last_verified_at", sa.Text(), nullable=True),
        sa.Column("trim_start_ms", sa.Integer(), nullable=True),
        sa.Column("trim_end_ms", sa.Integer(), nullable=True),
        sa.Column("focal_x", sa.Float(), nullable=True),
        sa.Column("focal_y", sa.Float(), nullable=True),
        sa.Column("last_rendered_at", sa.Text(), nullable=True),
        sa.Column("last_rendered_cache_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "role IN ('talking_head', 'screen_recording')",
            name="ck_media_assets_role",
        ),
        sa.CheckConstraint(
            "probe_status IN ('pending', 'ok', 'failed')",
            name="ck_media_assets_probe_status",
        ),
        sa.CheckConstraint("file_missing IN (0, 1)", name="ck_media_assets_file_missing"),
        sa.CheckConstraint(
            "has_audio IS NULL OR has_audio IN (0, 1)",
            name="ck_media_assets_has_audio",
        ),
        sa.CheckConstraint(
            "focal_x IS NULL OR (focal_x >= 0.0 AND focal_x <= 1.0)",
            name="ck_media_assets_focal_x",
        ),
        sa.CheckConstraint(
            "focal_y IS NULL OR (focal_y >= 0.0 AND focal_y <= 1.0)",
            name="ck_media_assets_focal_y",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "source_path", name="uq_media_assets_campaign_source"),
    )
    op.create_index(
        "ix_media_assets_campaign_role_order",
        "media_assets",
        ["campaign_id", "role", "sort_order"],
    )
    # DB.md §3.2: at most one talking head per campaign. Partial, because a
    # plain unique index on (campaign_id, role) would also forbid a second
    # screen recording — and a campaign is a batch of them.
    op.create_index(
        "uq_media_assets_one_talking_head",
        "media_assets",
        ["campaign_id"],
        unique=True,
        sqlite_where=sa.text("role = 'talking_head'"),
    )

    # --- DB.md §3.3 ---------------------------------------------------------
    op.create_table(
        "render_jobs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("campaign_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("queue_position", sa.Integer(), nullable=False),
        sa.Column("progress_pct", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        # Not a foreign key, deliberately: DB.md §3.3 deletes completed jobs
        # after export, and a self-referential FK would either block that or
        # cascade into jobs that are still queued.
        sa.Column("depends_on_job_id", sa.Text(), nullable=True),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.Column("output_filename", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column("ffmpeg_command", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "job_type IN ('alpha_prepare', 'video_render')",
            name="ck_render_jobs_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('waiting', 'preparing', 'rendering', 'encoding', 'completed', 'failed')",
            name="ck_render_jobs_status",
        ),
        sa.CheckConstraint(
            "progress_pct >= 0 AND progress_pct <= 100",
            name="ck_render_jobs_progress_pct",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_render_jobs_attempts"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_render_jobs_status_position", "render_jobs", ["status", "queue_position"])
    op.create_index("ix_render_jobs_campaign", "render_jobs", ["campaign_id"])
    op.create_index("ix_render_jobs_depends_on", "render_jobs", ["depends_on_job_id"])

    # --- DB.md §3.4 ---------------------------------------------------------
    op.create_table(
        "overlay_presets",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("overlay_config", sa.Text(), nullable=False),
        sa.Column("overlay_schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # --- DB.md §3.5 ---------------------------------------------------------
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quality_preset", sa.String(), nullable=False),
        sa.Column("encoder_override", sa.String(), nullable=True),
        sa.Column("default_export_path", sa.Text(), nullable=True),
        sa.Column("ffmpeg_version", sa.Text(), nullable=True),
        sa.Column("detected_encoders", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_app_settings_singleton"),
        sa.CheckConstraint(
            "quality_preset IN ('draft', 'standard', 'high')",
            name="ck_app_settings_quality_preset",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Q60: seeded here **and** self-healed at boot. A missing singleton is a
    # crash on every settings read, and the two mechanisms cover different
    # failures — this one covers a fresh database, the boot-time
    # `INSERT OR IGNORE` covers one somebody deleted the row from.
    #
    # The timestamp is a literal rather than `utcnow_iso()`: importing
    # application code into a migration is the thing this file exists not to do.
    op.execute(
        sa.text(
            "INSERT INTO app_settings "
            "(id, quality_preset, created_at, updated_at) "
            "VALUES (1, 'standard', "
            "strftime('%Y-%m-%dT%H:%M:%S', 'now') || '.000Z', "
            "strftime('%Y-%m-%dT%H:%M:%S', 'now') || '.000Z')"
        )
    )


def downgrade() -> None:
    # DB.md §7: the database is a user document and is never wiped to resolve a
    # schema problem. This exists because Alembic expects it, and because a
    # developer rolling back a *local* branch should not have to delete their
    # workspace by hand. It is not a supported user-facing operation.
    op.drop_table("app_settings")
    op.drop_table("overlay_presets")
    op.drop_index("ix_render_jobs_depends_on", table_name="render_jobs")
    op.drop_index("ix_render_jobs_campaign", table_name="render_jobs")
    op.drop_index("ix_render_jobs_status_position", table_name="render_jobs")
    op.drop_table("render_jobs")
    op.drop_index("uq_media_assets_one_talking_head", table_name="media_assets")
    op.drop_index("ix_media_assets_campaign_role_order", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_table("campaigns")
