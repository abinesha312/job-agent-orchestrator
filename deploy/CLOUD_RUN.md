# Cloud Run notes (Phase 8, NOT deployed)

Nothing in this repo deploys automatically. Sketch for later:

1. Cloud SQL for PostgreSQL 16 with the `vector` extension (`CREATE EXTENSION vector;`).
2. Secrets in Secret Manager: `DATABASE_URL`, `GEMINI_API_KEY` (or use Vertex AI with the
   service account), `APOLLO_API_KEY`, `ADZUNA_APP_ID/KEY`, `LANGFUSE_*`.
3. Build: `gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/job-agent/api:TAG -f deploy/Dockerfile .`
4. Migrate: run `alembic upgrade head` as a Cloud Run Job against Cloud SQL.
5. Deploy: `gcloud run deploy job-agent-api --image ... --add-cloudsql-instances PROJECT:REGION:INSTANCE
   --set-secrets DATABASE_URL=database-url:latest,... --set-env-vars EMBEDDING_BACKEND=litellm
   --no-allow-unauthenticated`
6. Cloud Tasks queue for discovery/tailoring jobs with rate limits; daily LLM budget cap.
7. Uploads: move `UPLOAD_DIR` to a GCS bucket (the local-disk store is dev-only).
8. Langfuse keys + alerts on error rate and spend.
