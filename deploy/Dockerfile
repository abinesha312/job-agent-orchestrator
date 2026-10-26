# Container for the FastAPI service (Cloud Run target). Not deployed; Phase 8.
# Build from repo root:  docker build -f deploy/Dockerfile -t job-agent:dev .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip install --no-cache-dir ".[llm]"

RUN useradd --create-home appuser
USER appuser

# Secrets (DATABASE_URL, GEMINI_API_KEY, ...) come from Secret Manager env bindings, never the image.
CMD exec uvicorn --factory job_agent.api.app:app_factory --host 0.0.0.0 --port ${PORT}
