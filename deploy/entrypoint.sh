#!/bin/sh
set -eu
if [ -n "${DATABASE_URL:-}" ]; then
  alembic upgrade head
fi
exec uvicorn --factory job_agent.api.app:app_factory --host 0.0.0.0 --port "${PORT:-8080}"
