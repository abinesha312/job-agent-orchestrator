"""Persistence for resume versions + chunks: in-memory (default/tests) or Postgres."""

from job_agent.storage.repository import (
    InMemoryResumeRepository,
    ResumeRepository,
    SqlResumeRepository,
    StoredChunk,
    StoredVersion,
)

__all__ = [
    "InMemoryResumeRepository",
    "ResumeRepository",
    "SqlResumeRepository",
    "StoredChunk",
    "StoredVersion",
]
