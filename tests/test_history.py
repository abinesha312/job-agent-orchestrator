from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from job_agent.api.app import create_app
from job_agent.config import Settings

DOC = {
    "generated_at": "2026-01-01T00:00:00-05:00",
    "status_definitions": {"confirmed": "has a confirmation"},
    "companies": [{"company_id": "acme", "name": "Acme"}],
    "jobs": [{"job_id": "acme-1", "company_id": "acme", "req_id": "1", "title": "Backend Engineer",
              "location": "Austin", "url": "https://example.com/1"}],
    "resumes": [{"resume_id": "V1_Backend", "version": "V1", "file_path": "x.docx"}],
    "applications": [{"application_id": "app-acme-1", "job_id": "acme-1", "resume_id": "V1_Backend",
                      "status": "confirmed", "applied_at": "2026-01-01T09:00:00-05:00",
                      "submitted_by_bot": "bot", "confirmation_source": "email", "notes": ""}],
    "events": [
        {"event_id": "e2", "application_id": "app-acme-1", "type": "rejection", "date": "2026-01-03", "detail": "no"},
        {"event_id": "e1", "application_id": "app-acme-1", "type": "confirmation_email", "date": "2026-01-01", "detail": "ok"},
    ],
}


@pytest.fixture()
def client(tmp_path):
    settings = Settings(database_url="", run_log_path=tmp_path / "r.jsonl", upload_dir=tmp_path,
                        history_path=tmp_path / "history.json")
    return TestClient(create_app(settings=settings)), settings


def _upload(c, doc):
    return c.post("/history/import", files={"file": ("e.json", io.BytesIO(json.dumps(doc).encode()))})


def test_empty_until_imported(client):
    c, _ = client
    assert c.get("/history/summary").json() == {"loaded": False}
    assert c.get("/history/applications").json()["total"] == 0


def test_import_joins_everything_and_persists(client):
    c, settings = client
    assert _upload(c, DOC).json()["totals"]["applications"] == 1
    row = c.get("/history/applications").json()["rows"][0]
    assert (row["company"], row["resume_version"], row["outcome"]) == ("Acme", "V1", "rejection")
    detail = c.get("/history/applications/app-acme-1").json()
    assert [e["event_id"] for e in detail["events"]] == ["e1", "e2"]
    assert c.get("/history/applications?status=blocked").json()["total"] == 0
    # a fresh app on the same path sees the saved file
    again = TestClient(create_app(settings=settings))
    assert again.get("/history/summary").json()["loaded"] is True


def test_bad_export_rejected_and_unknown_404(client):
    c, _ = client
    assert _upload(c, {"jobs": []}).status_code == 422
    assert c.get("/history/applications/nope").status_code == 404
