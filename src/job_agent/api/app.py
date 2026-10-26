"""FastAPI app: /health, POST /resumes, GET /resumes/{resume_id}/chunks."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from job_agent import __version__
from job_agent.agents.resume import ingest_resume
from job_agent.config import Settings, get_settings
from job_agent.embeddings.base import Embedder
from job_agent.embeddings.factory import get_embedder
from job_agent.parsing.extract import ResumeParseError, UnsupportedFileType
from job_agent.storage.repository import (
    InMemoryResumeRepository,
    ResumeRepository,
    SqlResumeRepository,
)


class HealthResponse(BaseModel):
    status: str
    version: str
    storage: str
    embedder: str


class ResumeUploadResponse(BaseModel):
    resume_id: uuid.UUID
    version_id: uuid.UUID
    version: int
    filename: str
    chunk_count: int
    sections: list[str]


class ChunkOut(BaseModel):
    id: uuid.UUID
    resume_id: uuid.UUID
    version: int
    section: str
    order: int
    text: str
    metadata: dict
    embedding_dim: int | None = None
    embedding: list[float] | None = None


class ChunksResponse(BaseModel):
    resume_id: uuid.UUID
    version: int
    count: int
    chunks: list[ChunkOut]


def _default_repository(settings: Settings) -> ResumeRepository:
    if not settings.database_url:
        return InMemoryResumeRepository()
    from job_agent.db.session import make_engine, make_session_factory

    return SqlResumeRepository(make_session_factory(make_engine(settings.database_url)))


def create_app(
    *,
    settings: Settings | None = None,
    repository: ResumeRepository | None = None,
    embedder: Embedder | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Job Agent Orchestrator", version=__version__)
    app.state.settings = settings
    app.state.repository = repository or _default_repository(settings)
    app.state.embedder = embedder or get_embedder(settings)

    @app.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        repo = request.app.state.repository
        return HealthResponse(
            status="ok",
            version=__version__,
            storage="postgres" if isinstance(repo, SqlResumeRepository) else "memory",
            embedder=request.app.state.embedder.name,
        )

    @app.post("/resumes", response_model=ResumeUploadResponse, status_code=201)
    async def upload_resume(
        request: Request,
        file: UploadFile = File(..., description="Resume as .pdf or .docx"),
        resume_id: uuid.UUID | None = Form(None, description="Existing resume_id to add a new version"),
    ) -> ResumeUploadResponse:
        s: Settings = request.app.state.settings
        repo: ResumeRepository = request.app.state.repository
        max_bytes = s.max_upload_mb * 1024 * 1024
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(413, f"File larger than {s.max_upload_mb} MB")
        if resume_id is not None and not repo.resume_exists(resume_id):
            raise HTTPException(404, f"resume_id {resume_id} not found")
        filename = file.filename or "resume"
        try:
            result = ingest_resume(
                data, filename,
                repository=repo,
                embedder=request.app.state.embedder,
                upload_dir=Path(s.upload_dir),
                resume_id=resume_id,
                max_chars=s.chunk_max_chars,
            )
        except UnsupportedFileType as exc:
            raise HTTPException(415, str(exc)) from exc
        except ResumeParseError as exc:
            raise HTTPException(422, str(exc)) from exc
        v = result.version
        return ResumeUploadResponse(
            resume_id=v.resume_id, version_id=v.version_id, version=v.version,
            filename=filename, chunk_count=len(result.chunks),
            sections=list(dict.fromkeys(c.section for c in result.chunks)),
        )

    @app.get("/resumes/{resume_id}/chunks", response_model=ChunksResponse)
    def get_chunks(
        request: Request,
        resume_id: uuid.UUID,
        version: int | None = Query(None, ge=1, description="Defaults to latest version"),
        section: str | None = Query(None),
        include_embeddings: bool = Query(False),
    ) -> ChunksResponse:
        repo: ResumeRepository = request.app.state.repository
        if not repo.resume_exists(resume_id):
            raise HTTPException(404, f"resume_id {resume_id} not found")
        chunks = repo.get_chunks(resume_id, version)
        if not chunks:
            raise HTTPException(404, f"No chunks for resume {resume_id} version {version}")
        if section:
            chunks = [c for c in chunks if c.section == section]
        out = [
            ChunkOut(
                id=c.id, resume_id=c.resume_id, version=c.version, section=c.section,
                order=c.order, text=c.text, metadata=c.metadata,
                embedding_dim=len(c.embedding) if c.embedding is not None else None,
                embedding=c.embedding if include_embeddings else None,
            )
            for c in chunks
        ]
        resolved = chunks[0].version if chunks else (version or 0)
        return ChunksResponse(resume_id=resume_id, version=resolved, count=len(out), chunks=out)

    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory job_agent.api.app:app_factory``."""
    return create_app()
