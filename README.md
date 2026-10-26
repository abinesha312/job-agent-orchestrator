# ApplyPilot

I built this to help me apply for jobs without the busywork. It reads a resume, pulls matching roles from public job boards, drafts a tailored resume and a short outreach note, and looks for a recruiter contact. I still approve everything. It never applies and it never sends email.

## The pieces

- Resume agent: parse a PDF or DOCX, split it into sections, store the chunks and embeddings.
- Job discovery: Greenhouse, Lever, and Ashby public boards, plus a job I paste in or a URL.
- Retrieval: embed the job description and pull the closest resume chunks.
- Tailoring: rewrite the resume for that job and draft a short email. If no LLM key is set it just reorders what is already on the resume.
- Email finder: look on the public posting and about/careers pages, otherwise guess a pattern and mark it unverified.
- Orchestrator: walk the job from discovered to matched to tailored to waiting for me. I approve or reject. Applied only happens when I mark it.

## Setup

Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"
cp .env.example .env
```

Leave `DATABASE_URL` empty to use memory, or start Postgres:

```bash
docker compose up -d db
alembic upgrade head
```

`docker compose up --build` also starts the API next to pgvector. The compose password is a throwaway local default.

## Run

```bash
uvicorn --factory job_agent.api.app:app_factory --reload
streamlit run ui/streamlit_app.py
```

The UI talks to `API_URL` (default `http://localhost:8000`).

Evals and tests:

```bash
python -m evals
pytest -q
ruff check .
```

`EMBEDDING_BACKEND=fake` is the offline default. Set `GEMINI_API_KEY` and `LLM_MODEL` if you want a real model. `LLM_JUDGE=auto` uses DeepEval only when a key is present. DB tests skip unless `TEST_DATABASE_URL` is set.

## Approval

Nothing here submits an application or sends mail. The database check constraint refuses `approved` or `applied` unless `approved_by_user` is true, and the only way to set that flag is the approve action. I mark a job applied after I have actually submitted it myself.

## Notes

Fixtures are fictional (Jordan Q. Sample, example.com). Don't commit a real resume. Scanned PDFs aren't supported. Email guesses are not verified. I didn't deploy this.
