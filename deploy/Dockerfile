# ApplyPilot: API plus the built Vue frontend in one image.
# docker build -f deploy/Dockerfile -t applypilot:dev .
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=7860 WEB_DIST=/app/web/dist
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
COPY evals ./evals
COPY deploy/entrypoint.sh /entrypoint.sh
COPY --from=web /web/dist ./web/dist
RUN pip install --no-cache-dir ".[llm]" && chmod +x /entrypoint.sh

RUN useradd --create-home appuser && mkdir -p /app/data && chown -R appuser /app/data
USER appuser

# DATABASE_URL, GEMINI_API_KEY and friends come from the environment, not the image.
ENTRYPOINT ["/entrypoint.sh"]
