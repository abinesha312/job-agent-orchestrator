"""SQLAlchemy models for the six pgvector tables in the plan.

Every table carries a ``metadata`` JSONB column and a ``created_at`` timestamp.
(The Python attribute is ``meta`` because ``metadata`` is reserved by SQLAlchemy's
declarative base; the database column is named ``metadata``.)
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Keep in sync with Settings.embedding_dim and the Alembic migration.
EMBEDDING_DIM = 768


class ApplicationStatus(enum.StrEnum):
    """Application lifecycle states, exactly as listed in the plan."""

    discovered = "discovered"
    matched = "matched"
    tailored = "tailored"
    awaiting_approval = "awaiting_approval"
    approved = "approved"
    applied = "applied"
    rejected = "rejected"


class Base(DeclarativeBase):
    pass


class MetadataMixin:
    meta: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResumeVersion(MetadataMixin, Base):
    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("resume_id", "version", name="uq_resume_versions_resume_version"),)

    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_versions.version_id", ondelete="SET NULL")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id", ondelete="SET NULL")
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)


class ResumeChunk(MetadataMixin, Base):
    __tablename__ = "resume_chunks"
    __table_args__ = (
        Index("ix_resume_chunks_resume_version", "resume_id", "version"),
        Index(
            "ix_resume_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_order: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class Job(MetadataMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index(
            "ix_jobs_jd_embedding_hnsw",
            "jd_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"jd_embedding": "vector_cosine_ops"},
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # greenhouse | lever | adzuna | manual
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    jd_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Match(MetadataMixin, Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("job_id", "resume_version", name="uq_matches_job_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False
    )
    resume_version: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_versions.version_id", ondelete="CASCADE"), nullable=False
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    missing_skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}"
    )


class Application(MetadataMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        # DB-level backstop for the approval gate: nothing can be marked applied
        # (or approved) unless the user approved it.
        CheckConstraint(
            "status NOT IN ('approved', 'applied') OR approved_by_user = true",
            name="ck_applications_approval_required",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status"),
        nullable=False,
        default=ApplicationStatus.discovered,
        server_default=ApplicationStatus.discovered.value,
    )
    approved_by_user: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Contact(MetadataMixin, Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="apollo", server_default="apollo")
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


ALL_TABLES = [
    "resume_chunks",
    "resume_versions",
    "jobs",
    "matches",
    "applications",
    "contacts",
]
