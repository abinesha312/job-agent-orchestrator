# Cloud Run notes

I have not deployed this. Nothing here signs you up for a paid service.

If I do it later:

1. Postgres 16 with pgvector (`CREATE EXTENSION vector`). Cloud SQL is the obvious place. Locally, `docker compose` is enough.
2. Put `DATABASE_URL` and, if I want a real model, `GEMINI_API_KEY` in Secret Manager. Leave them empty and the app still runs on the fake embedder and the plain rewrite.
3. Build the image from `deploy/Dockerfile` and run `alembic upgrade head` before serving. The entrypoint does that when `DATABASE_URL` is set.
4. Deploy the one container. Don't turn on unauthenticated public access unless I mean to.
5. Uploads are on local disk today (`UPLOAD_DIR`). A bucket would be the next move. I didn't do it.
6. Langfuse is optional. Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` if I want traces. The app runs fine without them.

Job boards used here are the public Greenhouse, Lever, and Ashby endpoints. No Adzuna key, no Apollo, no LinkedIn. Email guesses stay unverified and nothing is sent.

The approval check constraint stays in the database. A Cloud Run deploy doesn't change that.
