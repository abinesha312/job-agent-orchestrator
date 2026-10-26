"""Pluggable embedders: deterministic fake (offline/tests) or LiteLLM (Gemini default)."""

from job_agent.embeddings.base import Embedder
from job_agent.embeddings.factory import get_embedder
from job_agent.embeddings.fake import FakeEmbedder

__all__ = ["Embedder", "FakeEmbedder", "get_embedder"]
