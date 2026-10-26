"""Initial schema: pgvector + the 6 tables from the plan.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

DIM = 768  # must match job_agent.db.models.EMBEDDING_DIM / EMBEDDING_DIM env
STATUSES = ("discovered", "matched", "tailored", "awaiting_approval", "approved", "applied", "rejected")


def _common() -> list[sa.Column]:
    return [
        sa.Column("metadata", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "jobs",
        sa.Column("job_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("jd_embedding", Vector(DIM)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        *_common(),
    )
    op.execute(
        "CREATE INDEX ix_jobs_jd_embedding_hnsw ON jobs USING hnsw (jd_embedding vector_cosine_ops)"
    )

    op.create_table(
        "resume_versions",
        sa.Column("version_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("resume_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("resume_versions.version_id", ondelete="SET NULL")),
        sa.Column("job_id", pg.UUID(as_uuid=True), sa.ForeignKey("jobs.job_id", ondelete="SET NULL")),
        sa.Column("file_path", sa.Text(), nullable=False),
        *_common(),
        sa.UniqueConstraint("resume_id", "version", name="uq_resume_versions_resume_version"),
    )
    op.create_index("ix_resume_versions_resume_id", "resume_versions", ["resume_id"])

    op.create_table(
        "resume_chunks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("resume_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(64), nullable=False),
        sa.Column("chunk_order", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(DIM)),
        *_common(),
    )
    op.create_index("ix_resume_chunks_resume_version", "resume_chunks", ["resume_id", "version"])
    op.execute(
        "CREATE INDEX ix_resume_chunks_embedding_hnsw ON resume_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "matches",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", pg.UUID(as_uuid=True), sa.ForeignKey("jobs.job_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("resume_version", pg.UUID(as_uuid=True),
                  sa.ForeignKey("resume_versions.version_id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("missing_skills", pg.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        *_common(),
        sa.UniqueConstraint("job_id", "resume_version", name="uq_matches_job_version"),
    )

    status_enum = pg.ENUM(*STATUSES, name="application_status")
    status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "applications",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", pg.UUID(as_uuid=True), sa.ForeignKey("jobs.job_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("status", pg.ENUM(*STATUSES, name="application_status", create_type=False),
                  nullable=False, server_default="discovered"),
        sa.Column("approved_by_user", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        *_common(),
        sa.CheckConstraint(
            "status NOT IN ('approved', 'applied') OR approved_by_user = true",
            name="ck_applications_approval_required",
        ),
    )
    op.create_index("ix_applications_job_id", "applications", ["job_id"])

    op.create_table(
        "contacts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", pg.UUID(as_uuid=True), sa.ForeignKey("jobs.job_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("email", sa.String(320)),
        sa.Column("source", sa.String(32), nullable=False, server_default="apollo"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_common(),
    )
    op.create_index("ix_contacts_job_id", "contacts", ["job_id"])


def downgrade() -> None:
    op.drop_table("contacts")
    op.drop_table("applications")
    pg.ENUM(name="application_status").drop(op.get_bind(), checkfirst=True)
    op.drop_table("matches")
    op.drop_table("resume_chunks")
    op.drop_table("resume_versions")
    op.drop_table("jobs")
