"""Integration tests against real Postgres + pgvector.

Skipped unless TEST_DATABASE_URL is set, e.g. with `docker compose up -d db`:
  TEST_DATABASE_URL=postgresql+psycopg://job_agent:job_agent@localhost:5432/job_agent
Runs the Alembic migration, so point it at a throwaway database.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [pytest.mark.db, pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")]
ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def engine():
    from alembic.config import Config
    from sqlalchemy import create_engine

    from alembic import command

    os.environ["DATABASE_URL"] = URL
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng = create_engine(URL)
    yield eng
    eng.dispose()
    command.downgrade(cfg, "base")


def test_schema_has_all_tables_with_metadata_and_created_at(engine):
    from sqlalchemy import inspect

    from job_agent.db.models import ALL_TABLES

    insp = inspect(engine)
    for t in ALL_TABLES:
        cols = {c["name"] for c in insp.get_columns(t)}
        assert {"metadata", "created_at"} <= cols, t


def test_status_enum_and_approval_check_constraint(engine):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with engine.connect() as c:
        vals = c.execute(text("SELECT unnest(enum_range(NULL::application_status))::text")).scalars().all()
    assert vals == ["discovered", "matched", "tailored", "awaiting_approval", "approved", "applied", "rejected"]

    job_id = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO jobs (job_id, company, title, source, url, jd_text) "
                       "VALUES (:j, 'Example Corp', 'BE', 'manual', :u, 'jd')"),
                  {"j": job_id, "u": f"https://example.com/{job_id}"})
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("INSERT INTO applications (id, job_id, status, approved_by_user) "
                       "VALUES (:i, :j, 'applied', false)"), {"i": uuid.uuid4(), "j": job_id})
    with engine.begin() as c:
        c.execute(text("INSERT INTO applications (id, job_id, status, approved_by_user) "
                       "VALUES (:i, :j, 'applied', true)"), {"i": uuid.uuid4(), "j": job_id})


def test_api_against_postgres(engine, pdf_bytes, tmp_path):
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from job_agent.api.app import create_app
    from job_agent.config import Settings
    from job_agent.embeddings import FakeEmbedder

    app = create_app(settings=Settings(database_url=URL, upload_dir=tmp_path), embedder=FakeEmbedder(768))
    client = TestClient(app)
    assert client.get("/health").json()["storage"] == "postgres"
    up = client.post("/resumes", files={"file": ("r.pdf", pdf_bytes, "application/pdf")}).json()
    up2 = client.post("/resumes", files={"file": ("r.pdf", pdf_bytes, "application/pdf")},
                      data={"resume_id": up["resume_id"]}).json()
    assert up2["version"] == 2
    chunks = client.get(f"/resumes/{up['resume_id']}/chunks", params={"version": 1}).json()
    assert chunks["count"] == up["chunk_count"]
    assert chunks["chunks"][0]["metadata"]["version_id"] == up["version_id"]

    # pgvector cosine query works on the stored embeddings
    q = FakeEmbedder(768).embed(["Prometheus metrics Grafana dashboards on-call"])[0]
    with engine.connect() as c:
        top = c.execute(text("SELECT section FROM resume_chunks WHERE resume_id = :r AND version = 1 "
                             "ORDER BY embedding <=> CAST(:q AS vector) LIMIT 1"),
                        {"r": up["resume_id"], "q": str(q)}).scalar()
        parent = c.execute(text("SELECT parent_id FROM resume_versions WHERE version_id = :v"),
                           {"v": up2["version_id"]}).scalar()
    assert top == "experience"
    assert str(parent) == up["version_id"]
