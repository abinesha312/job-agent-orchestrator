"""Resume agent (Phase 1, REAL): parse an uploaded PDF/DOCX, chunk it by section,
embed the chunks, and store them with metadata as a new resume version."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from job_agent.embeddings.base import Embedder
from job_agent.parsing.chunker import Chunk, chunk_resume
from job_agent.parsing.extract import extract_text, file_type_for
from job_agent.storage.repository import ResumeRepository, StoredVersion
from job_agent.tracing.langfuse_hook import trace_step

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class IngestResult:
    version: StoredVersion
    chunks: list[Chunk]


def parse_and_chunk(data: bytes, filename: str, *, resume_id: str, version: int,
                    max_chars: int = 800) -> list[Chunk]:
    """Pure function: bytes -> section-aware chunks with metadata. No I/O."""
    file_type = file_type_for(filename)
    text = extract_text(data, filename)
    return chunk_resume(
        text, resume_id=resume_id, version=version, max_chars=max_chars,
        extra_metadata={"source_filename": filename, "file_type": file_type},
    )


@trace_step("resume_agent.ingest")
def ingest_resume(
    data: bytes,
    filename: str,
    *,
    repository: ResumeRepository,
    embedder: Embedder,
    upload_dir: Path,
    resume_id: uuid.UUID | None = None,
    max_chars: int = 800,
) -> IngestResult:
    """Parse, chunk, embed and persist a resume. Pass ``resume_id`` to add a new version."""
    file_type_for(filename)  # fail fast on unsupported extensions
    resume_id = resume_id or uuid.uuid4()
    version = repository.next_version(resume_id)

    chunks = parse_and_chunk(data, filename, resume_id=str(resume_id), version=version,
                             max_chars=max_chars)
    embeddings = embedder.embed([c.text for c in chunks])
    for c in chunks:
        c.metadata["embedding_model"] = embedder.name

    safe = _SAFE_NAME_RE.sub("_", Path(filename).name) or "resume"
    dest = Path(upload_dir) / str(resume_id) / f"v{version}_{safe}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    stored = repository.save_version(
        resume_id=resume_id,
        version=version,
        file_path=str(dest),
        metadata={
            "source_filename": filename,
            "sha256": hashlib.sha256(data).hexdigest(),
            "chunk_count": len(chunks),
            "sections": sorted({c.section for c in chunks}),
            "embedding_model": embedder.name,
            "kind": "original",
        },
        chunks=chunks,
        embeddings=embeddings,
    )
    return IngestResult(stored, chunks)
