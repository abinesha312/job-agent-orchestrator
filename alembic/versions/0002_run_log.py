"""run_log so a failed job is visible after the process exits.

Revision ID: 0002_run_log
Revises: 0001_initial
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0002_run_log"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_log",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", pg.UUID(as_uuid=True), sa.ForeignKey("jobs.job_id", ondelete="SET NULL")),
        sa.Column("resume_id", pg.UUID(as_uuid=True)),
        sa.Column("step", sa.String(64), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_run_log_created", "run_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_run_log_created", table_name="run_log")
    op.drop_table("run_log")
