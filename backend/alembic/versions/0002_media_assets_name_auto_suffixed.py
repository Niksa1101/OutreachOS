"""Add name_auto_suffixed to media_assets.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05

Persist whether a screen-recording company name was auto-suffixed at import or
rename time, rather than inferring it from the string after the fact.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The server default only exists to backfill existing rows; it is dropped
    # immediately so the live schema matches the model, which declares a
    # Python-side default only (the ``file_missing`` convention from 0001).
    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.add_column(
            sa.Column("name_auto_suffixed", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_check_constraint(
            "ck_media_assets_name_auto_suffixed",
            "name_auto_suffixed IN (0, 1)",
        )

    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.alter_column(
            "name_auto_suffixed",
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.drop_constraint("ck_media_assets_name_auto_suffixed", type_="check")
        batch_op.drop_column("name_auto_suffixed")
