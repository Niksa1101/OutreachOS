"""Add run_id to render_jobs for batch-progress scoping.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-07

Ticket 18's batch header must describe the current Generate/Retry run, not
every historical row. ``run_id`` groups jobs enqueued together; completed rows
stay in the table (history) until P5 export prunes them.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("render_jobs") as batch_op:
        batch_op.add_column(sa.Column("run_id", sa.Text(), nullable=True))
        batch_op.create_index("ix_render_jobs_run_id", ["run_id"])


def downgrade() -> None:
    with op.batch_alter_table("render_jobs") as batch_op:
        batch_op.drop_index("ix_render_jobs_run_id")
        batch_op.drop_column("run_id")
