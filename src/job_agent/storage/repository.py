"""Resume repository interface with in-memory and SQLAlchemy/pgvector implementations."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from job_agent.db.models import ResumeChunk, ResumeVersion
from job_agent.parsing.chunker import Chunk


@dataclass
class StoredVersion:
    version_id: uuid.UUID
    resume_id: uuid.UUID
    version: int
    file_path: str
    metadata: dict
    created_at: datetime
    parent_id: uuid.UUID | None = None


@dataclass
class StoredChunk:
    id: uuid.UUID
    resume_id: uuid.UUID
    version: int
    section: str
    order: int
    text: str
    metadata: dict
    created_at: datetime
    embedding: list[float] | None = field(default=None, repr=False)


class ResumeRepository(Protocol):
    def next_version(self, resume_id: uuid.UUID) -> int: ...

    def save_version(
        self,
        *,
        resume_id: uuid.UUID,
        version: int,
        file_path: str,
        metadata: dict,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> StoredVersion: ...

    def resume_exists(self, resume_id: uuid.UUID) -> bool: ...

    def get_chunks(self, resume_id: uuid.UUID, version: int | None = None) -> list[StoredChunk]: ...


def _now() -> datetime:
    return datetime.now(UTC)


class InMemoryResumeRepository:
    """Process-local store. Used when DATABASE_URL is unset and in API tests."""

    def __init__(self) -> None:
        self._versions: dict[uuid.UUID, list[StoredVersion]] = {}
        self._chunks: dict[tuple[uuid.UUID, int], list[StoredChunk]] = {}
        self._lock = threading.Lock()

    def next_version(self, resume_id: uuid.UUID) -> int:
        return len(self._versions.get(resume_id, [])) + 1

    def save_version(self, *, resume_id, version, file_path, metadata, chunks, embeddings):
        with self._lock:
            versions = self._versions.setdefault(resume_id, [])
            parent = versions[-1].version_id if versions else None
            sv = StoredVersion(uuid.uuid4(), resume_id, version, file_path, dict(metadata), _now(), parent)
            versions.append(sv)
            self._chunks[(resume_id, version)] = [
                StoredChunk(uuid.uuid4(), resume_id, version, c.section, c.order, c.text,
                            dict(c.metadata), _now(), emb)
                for c, emb in zip(chunks, embeddings, strict=True)
            ]
            return sv

    def resume_exists(self, resume_id: uuid.UUID) -> bool:
        return resume_id in self._versions

    def get_chunks(self, resume_id, version=None):
        versions = self._versions.get(resume_id)
        if not versions:
            return []
        v = version if version is not None else versions[-1].version
        return sorted(self._chunks.get((resume_id, v), []), key=lambda c: c.order)


class SqlResumeRepository:
    """Postgres + pgvector store (tables from the Alembic migration)."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def next_version(self, resume_id: uuid.UUID) -> int:
        with self._sf() as s:
            current = s.scalar(
                select(func.max(ResumeVersion.version)).where(ResumeVersion.resume_id == resume_id)
            )
            return (current or 0) + 1

    def save_version(self, *, resume_id, version, file_path, metadata, chunks, embeddings):
        with self._sf.begin() as s:
            parent = s.scalar(
                select(ResumeVersion.version_id)
                .where(ResumeVersion.resume_id == resume_id)
                .order_by(ResumeVersion.version.desc())
                .limit(1)
            )
            rv = ResumeVersion(
                resume_id=resume_id, version=version, file_path=file_path,
                parent_id=parent, meta=dict(metadata),
            )
            s.add(rv)
            s.flush()
            for c, emb in zip(chunks, embeddings, strict=True):
                s.add(ResumeChunk(
                    resume_id=resume_id, version=version, section=c.section,
                    chunk_order=c.order, text=c.text, embedding=emb,
                    meta={**c.metadata, "version_id": str(rv.version_id)},
                ))
            s.flush()
            s.refresh(rv)
            return StoredVersion(rv.version_id, rv.resume_id, rv.version, rv.file_path,
                                 rv.meta, rv.created_at, rv.parent_id)

    def resume_exists(self, resume_id: uuid.UUID) -> bool:
        with self._sf() as s:
            return s.scalar(
                select(func.count()).select_from(ResumeVersion).where(ResumeVersion.resume_id == resume_id)
            ) > 0

    def get_chunks(self, resume_id, version=None):
        with self._sf() as s:
            if version is None:
                version = s.scalar(
                    select(func.max(ResumeVersion.version)).where(ResumeVersion.resume_id == resume_id)
                )
                if version is None:
                    return []
            rows = s.scalars(
                select(ResumeChunk)
                .where(ResumeChunk.resume_id == resume_id, ResumeChunk.version == version)
                .order_by(ResumeChunk.chunk_order)
            ).all()
            return [
                StoredChunk(r.id, r.resume_id, r.version, r.section, r.chunk_order, r.text,
                            r.meta, r.created_at,
                            list(r.embedding) if r.embedding is not None else None)
                for r in rows
            ]
