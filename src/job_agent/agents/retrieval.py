"""Retrieval agent — STUB (Phase 2-3).

Purpose: given a job, return the resume chunks most relevant to its JD, for the
tailoring agent and for the "retrieval precision >= 0.8 on top-5" eval gate.

TODO(phase-2):
  - Embed the JD (or reuse jobs.jd_embedding) with the same embedder as the chunks.
  - Query pgvector, e.g.::

        SELECT id, section, text, 1 - (embedding <=> :q) AS score
        FROM resume_chunks
        WHERE resume_id = :rid AND version = :ver
        ORDER BY embedding <=> :q
        LIMIT :k;

  - Optionally boost by section (skills/experience) and de-duplicate near-identical chunks.
  - Compute match_score + missing_skills and write a ``matches`` row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    section: str
    text: str
    score: float


def retrieve_chunks_for_job(job_id: uuid.UUID, resume_id: uuid.UUID, *, version: int | None = None,
                            k: int = 5) -> list[RetrievedChunk]:
    raise NotImplementedError("Phase 2: retrieval agent not implemented yet")


def score_match(job_id: uuid.UUID, resume_version_id: uuid.UUID) -> tuple[float, list[str]]:
    """Return (match_score, missing_skills). TODO(phase-2)."""
    raise NotImplementedError("Phase 2: match scoring not implemented yet")
