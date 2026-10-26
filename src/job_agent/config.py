"""Application settings loaded from environment variables / a local .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"

    # Empty string => in-memory repository (no DB needed).
    database_url: str = ""

    # "fake" (deterministic, offline) or "litellm" (Gemini by default).
    embedding_backend: str = "fake"
    embedding_model: str = "gemini/gemini-embedding-001"
    # Must match the vector(N) width in the Alembic migration (768).
    embedding_dim: int = 768

    upload_dir: Path = Path("./data/uploads")
    max_upload_mb: int = 10

    # Chunking
    chunk_max_chars: int = 800


@lru_cache
def get_settings() -> Settings:
    return Settings()
