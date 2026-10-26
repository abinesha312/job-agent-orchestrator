# ApplyPilot API. Not deployed from this repo.
# docker build -f deploy/Dockerfile -t applypilot:dev .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
COPY evals ./evals
COPY deploy/entrypoint.sh /entrypoint.sh
RUN pip install --no-cache-dir ".[llm]" && chmod +x /entrypoint.sh

RUN useradd --create-home appuser
USER appuser

# DATABASE_URL, GEMINI_API_KEY and friends come from the environment, not the image.
ENTRYPOINT ["/entrypoint.sh"]
