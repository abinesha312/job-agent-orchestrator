from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from job_agent.agents.registry import SUBAGENTS
from job_agent.api.app import create_app
from job_agent.config import Settings


@pytest.fixture()
def client(tmp_path):
    settings = Settings(database_url="", run_log_path=tmp_path / "runs.jsonl", upload_dir=tmp_path)
    return TestClient(create_app(settings=settings))


def test_agents_overview_lists_main_and_subagents(client):
    body = client.get("/agents").json()
    assert body["main"]["id"] == "orchestrator"
    assert [s["id"] for s in body["subagents"]] == [s.id for s in sorted(SUBAGENTS, key=lambda s: s.order)]
    assert all(s["state"] == "idle" for s in body["subagents"])


def test_job_import_shows_up_as_discovery_task(client):
    client.post("/jobs/import", json={
        "company": "Example Corp", "title": "Backend Engineer",
        "url": "https://example.com/j", "jd_text": "Must have: Python, FastAPI.",
    })
    discovery = next(s for s in client.get("/agents").json()["subagents"] if s["id"] == "discovery")
    assert discovery["tasks_total"] == 1
    assert client.get("/agents/timeline").json()["count"] == 1


@pytest.mark.parametrize("suite", ["retrieval", "generation", "format", "safety", "gates"])
def test_offline_suites_pass_on_golden_set(client, suite):
    r = client.post("/evals/run", json={"suite": suite}).json()
    assert r["status"] == "passed", r["cases"]
    assert r["total"] >= 20


def test_engine_suites_skip_cleanly_without_keys(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for suite in ("ragas", "deepeval", "live"):
        r = client.post("/evals/run", json={"suite": suite}).json()
        assert r["status"] == "skipped" and r["notes"]


def test_unknown_suite_404_and_history(client):
    assert client.post("/evals/run", json={"suite": "nope"}).status_code == 404
    client.post("/evals/run", json={"suite": "format"})
    runs = client.get("/evals/runs").json()["runs"]
    assert len(runs) == 1 and "cases" not in runs[0]
    assert client.get(f"/evals/runs/{runs[0]['id']}").json()["suite"] == "format"
