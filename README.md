# Job Agent Orchestrator

A Python multi-agent system that parses a resume, will match and tailor it to job postings,
find recruiter contacts, and queue applications **for your approval**. Nothing is submitted
or emailed automatically, and there is no auto-submit mode.

> **Status: Phase 1 (foundation) only.** Resume upload, parsing, chunking, embeddings, the
> pgvector schema and the approval gate work. Everything else is a stub that raises
> `NotImplementedError`. Nothing here is deployed.

## Status by phase

| Phase | Scope (from plan) | Status | What exists |
|---|---|---|---|
| 1 | Repo, FastAPI skeleton, pgvector schema, resume upload/parsing | **Built** | `/health`, `POST /resumes`, `GET /resumes/{id}/chunks`; PDF/DOCX parsing; section-aware chunks with metadata; pluggable embeddings (fake offline + LiteLLM/Gemini); SQLAlchemy models + Alembic migration for all 6 tables; in-memory and Postgres repositories; tests |
| 1 | Approval gate | **Built (logic)** | `approval/gate.py`: status state machine, `approve()` as the only way to set `approved_by_user=True`, `@requires_approval` on submit/send, plus a DB CHECK constraint. The submit/send functions themselves are stubs |
| 2-3 | Retrieval + tailoring agents, versioning, DeepEval suite | Stub | `agents/retrieval.py` and `agents/tailoring.py` signatures and TODOs; `evals/gates.py` thresholds and a working `keyword_coverage()`; `evals/deepeval_suite.py` skeleton (skipped) |
| 4 | Job discovery (Greenhouse, Lever, Adzuna) | Stub | `agents/job_discovery.py` with endpoints and TODOs |
| 5 | Apollo email finder + contacts | Stub | `agents/email_finder.py` (only finds contacts, never sends); `contacts` table exists |
| 6 | Orchestrator, status tracking, approval queue | Stub (interface) | `agents/orchestrator.py`: `Orchestrator` ABC with state-machine, Microsoft Agent Framework and AutoGen adapters (all stubs) |
| 7 | Streamlit UI | Partial stub | `ui/streamlit_app.py` can upload a resume and show its chunks through the API; the approval queue is a TODO |
| 8 | Cloud Run deploy, Langfuse, alerts, rate limits | Stub | `deploy/Dockerfile` (not built in CI), `deploy/CLOUD_RUN.md` notes, `tracing/langfuse_hook.py` (a no-op decorator) |

## Layout

```
src/job_agent/
  api/app.py            FastAPI app factory
  config.py             env settings (pydantic-settings)
  db/models.py          6 tables + ApplicationStatus enum (pgvector)
  parsing/              extract.py (pypdf / python-docx), chunker.py (section-aware)
  embeddings/           fake.py (deterministic), litellm_embedder.py (Gemini default), factory.py
  storage/repository.py in-memory + SQLAlchemy repositories
  agents/               resume (real), retrieval, tailoring, job_discovery, email_finder, orchestrator
  approval/gate.py      mandatory approval gate
  tracing/langfuse_hook.py
alembic/                migration 0001 (source of truth); sql/schema.sql is generated reference DDL
evals/                  gate thresholds + DeepEval skeleton
ui/streamlit_app.py     UI stub
deploy/                 Dockerfile + Cloud Run notes
tests/                  pytest (synthetic fixtures only)
```

## Data model

All six tables have `metadata JSONB` and `created_at`. Vectors are `vector(768)` with HNSW cosine indexes.

| Table | Fields |
|---|---|
| resume_chunks | id, resume_id, version, section, chunk_order, text, embedding |
| resume_versions | version_id, resume_id, version, parent_id, job_id, file_path |
| jobs | job_id, company, title, source, url (unique), jd_text, jd_embedding, posted_at |
| matches | id, job_id, resume_version → resume_versions.version_id, match_score, missing_skills text[] |
| applications | id, job_id, status (`application_status` enum), approved_by_user, applied_at; CHECK: approved/applied requires approved_by_user |
| contacts | id, job_id, name, title, email, source (default `apollo`), verified |

Status values: `discovered, matched, tailored, awaiting_approval, approved, applied, rejected`.

## Run locally

Requires Python 3.11+. Tests and the default config need **no API keys and no database**.

```bash
uv venv && source .venv/bin/activate        # or: python -m venv .venv
uv pip install -e ".[dev]"                   # or: pip install -e ".[dev]"
pytest                                       # DB tests skip unless TEST_DATABASE_URL is set

cp .env.example .env                         # optional; leave DATABASE_URL empty for in-memory
uvicorn --factory job_agent.api.app:app_factory --reload
curl localhost:8000/health
curl -F file=@my_resume.pdf localhost:8000/resumes
curl "localhost:8000/resumes/<resume_id>/chunks?section=skills"
```

Interactive docs: http://localhost:8000/docs. To upload a new version of an existing resume,
POST with the form field `resume_id=<id>`.

### With Postgres + pgvector

```bash
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://job_agent:job_agent@localhost:5432/job_agent
alembic upgrade head
TEST_DATABASE_URL=$DATABASE_URL pytest -m db   # warning: downgrades/recreates the schema
```

The compose credentials are throwaway local defaults.

### Real embeddings (optional, uses a paid API)

```bash
uv pip install -e ".[llm]"
export EMBEDDING_BACKEND=litellm GEMINI_API_KEY=...   # default model gemini/gemini-embedding-001 @ 768 dims
```

## Safety rules

- **Approval is required for every application and email.** `submit_application` and
  `send_outreach_email` raise `ApprovalRequiredError` unless `approved_by_user is True` and the
  status is `approved`. Agents cannot self-approve: `transition(..., "approved")` raises.
- Official APIs only (Greenhouse, Lever, Adzuna, Apollo). No LinkedIn scraping and no CAPTCHA bypass.
- Never commit secrets. Only `.env.example` is tracked. Test fixtures use a fictional person.

## Notes and deviations from the plan

- **Orchestrator:** the plan names AutoGen. As of Oct 2026 the AutoGen repo is archived and
  Microsoft points users to Microsoft Agent Framework (1.0 GA in April 2026). The default is
  therefore a plain-Python state machine, with MAF and AutoGen adapters behind the same interface.
- **Local dev uses docker-compose pgvector** instead of Cloud SQL. Cloud SQL is planned for Phase 8.
- Extra columns beyond the plan's "key fields": surrogate `id` PKs, `resume_versions.resume_id`
  and `.version` (to link versions to chunks), and `resume_chunks.chunk_order`.
- Uploaded files are stored on local disk (`UPLOAD_DIR`). Moving them to GCS is planned for Phase 8.
- Scanned or image-only PDFs need OCR, which is not implemented. They return 422.
- The fake embedder uses lexical feature hashing. It is deterministic and works offline, but it is not semantic.
