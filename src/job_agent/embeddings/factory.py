from __future__ import annotations

from job_agent.config import Settings, get_settings
from job_agent.embeddings.base import Embedder
from job_agent.embeddings.fake import FakeEmbedder


def get_embedder(settings: Settings | None = None) -> Embedder:
    settings = settings or get_settings()
    backend = settings.embedding_backend.lower()
    if backend == "fake":
        return FakeEmbedder(dim=settings.embedding_dim)
    if backend == "litellm":
        from job_agent.embeddings.litellm_embedder import LiteLLMEmbedder

        return LiteLLMEmbedder(model=settings.embedding_model, dim=settings.embedding_dim)
    raise ValueError(f"Unknown EMBEDDING_BACKEND {settings.embedding_backend!r} (use fake|litellm)")
