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
    run_log_path: Path = Path("./data/run_log.jsonl")
    max_upload_mb: int = 10

    # Chunking
    chunk_max_chars: int = 800

    # Tailoring. Empty key => deterministic rewrite, no network.
    llm_model: str = "gemini/gemini-2.5-flash"
    gemini_api_key: str = ""
    # auto uses DeepEval only when a key is present; tests force this off
    llm_judge: str = "auto"
    daily_llm_calls: int = 40

    http_timeout_s: float = 15.0
    http_retries: int = 3
    retrieval_k: int = 5

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
