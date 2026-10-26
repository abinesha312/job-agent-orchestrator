import httpx
import respx
from fastapi.testclient import TestClient

from job_agent.api.app import create_app
from job_agent.config import Settings
from job_agent.embeddings.fake import FakeEmbedder
from job_agent.storage.pipeline import InMemoryPipelineStore
from job_agent.storage.repository import InMemoryResumeRepository

GH = {
    "jobs": [
        {
            "id": 101,
            "title": "Backend Engineer",
            "absolute_url": "https://boards.greenhouse.io/example/jobs/101",
            "updated_at": "2026-01-02T00:00:00Z",
            "company_name": "Example Corp",
            "content": (
                "<h1>Backend Engineer</h1><p>Example Corp (fictional).</p>"
                "<p>Must have: Python, FastAPI, PostgreSQL, Docker.</p>"
                "<p>Nice to have: Kubernetes.</p>"
            ),
        }
    ]
}

JD = (
    "Example Corp (fictional) — Backend Engineer\n"
    "Must have: Python, FastAPI, PostgreSQL, Docker.\n"
)


def _client(tmp_path):
    settings = Settings(
        database_url="", upload_dir=tmp_path / "up", run_log_path=tmp_path / "runs.jsonl",
        llm_judge="off", http_retries=1,
    )
    store = InMemoryPipelineStore(tmp_path / "runs.jsonl")
    app = create_app(
        settings=settings,
        repository=InMemoryResumeRepository(),
        store=store,
        embedder=FakeEmbedder(768),
    )
    return TestClient(app), store


def test_full_flow(tmp_path, docx_bytes):
    client, store = _client(tmp_path)
    up = client.post("/resumes", files={"file": ("resume.docx", docx_bytes, "application/octet-stream")})
    assert up.status_code == 201, up.text
    resume_id = up.json()["resume_id"]

    with respx.mock:
        respx.get(url__regex=r"https://boards-api\.greenhouse\.io/.*").mock(
            return_value=httpx.Response(200, json=GH)
        )
        respx.get(url__regex=r"https://api\.lever\.co/.*").mock(
            return_value=httpx.Response(404, text="missing board")
        )
        # email finder and anything else
        respx.get(url__regex=r".*").mock(return_value=httpx.Response(404, text="no"))
        disc = client.post("/discovery", json={
            "greenhouse": ["example"], "lever": ["missing-co"], "roles": ["backend"],
        })
    assert disc.status_code == 200, disc.text
    body = disc.json()
    assert body["saved"] == 1
    assert body["errors"]  # lever failed, greenhouse didn't
    job_id = body["job_ids"][0]

    with respx.mock:
        respx.get(url__regex=r".*").mock(return_value=httpx.Response(404, text="no"))
        ran = client.post("/pipeline/run", json={"resume_id": resume_id, "job_ids": [job_id]})
    assert ran.status_code == 200, ran.text
    result = ran.json()["results"][0]
    assert result["status"] == "awaiting_approval", result

    apps = client.get("/applications").json()["applications"]
    assert len(apps) == 1
    app_id = apps[0]["id"]
    assert apps[0]["eval_blocked"] is False

    draft = client.get(f"/applications/{app_id}/draft")
    assert draft.status_code == 200
    assert "Python" in draft.json()["resume_text"]
    assert draft.json()["contacts"]
    assert all(c["verified"] is False for c in draft.json()["contacts"])

    # mark applied before approval is refused
    early = client.post(f"/applications/{app_id}/applied")
    assert early.status_code == 409

    bad = client.post(f"/applications/{app_id}/approve", json={"approved_by": "  "})
    assert bad.status_code == 409

    ok = client.post(f"/applications/{app_id}/approve", json={"approved_by": "abinesh"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved"
    assert ok.json()["approved_by_user"] is True

    docx = client.get(f"/applications/{app_id}/docx")
    assert docx.status_code == 200
    assert docx.content[:2] == b"PK"

    applied = client.post(f"/applications/{app_id}/applied")
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert applied.json()["applied_at"]

    # still exactly one application, and the send path is not an endpoint that fires mail
    assert len(store.list_applications()) == 1
    runs = client.get("/runs").json()["runs"]
    assert runs


def test_edit_that_invents_a_skill_is_blocked(tmp_path, docx_bytes):
    client, _store = _client(tmp_path)
    resume_id = client.post(
        "/resumes", files={"file": ("resume.docx", docx_bytes, "application/octet-stream")}
    ).json()["resume_id"]
    job = client.post("/jobs/import", json={
        "company": "Example Corp", "title": "Backend Engineer",
        "url": "https://example.com/jobs/9", "jd_text": JD,
    })
    assert job.status_code == 201, job.text
    with respx.mock:
        respx.get(url__regex=r".*").mock(return_value=httpx.Response(404, text="no"))
        ran = client.post("/pipeline/run", json={"resume_id": resume_id})
    assert ran.json()["results"][0]["status"] == "awaiting_approval"
    app_id = client.get("/applications").json()["applications"][0]["id"]
    draft = client.get(f"/applications/{app_id}/draft").json()
    poisoned = draft["resume_text"] + "\nSKILLS\nRust, COBOL\n• Invented a staff role at Stripe.\n"
    edited = client.patch(f"/applications/{app_id}/draft", json={"resume_text": poisoned})
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["eval_blocked"] is True
    assert body["status"] == "tailored"
    denied = client.post(f"/applications/{app_id}/approve", json={"approved_by": "abinesh"})
    assert denied.status_code == 409


def test_reject(tmp_path, docx_bytes):
    client, _store = _client(tmp_path)
    resume_id = client.post(
        "/resumes", files={"file": ("resume.docx", docx_bytes, "application/octet-stream")}
    ).json()["resume_id"]
    client.post("/jobs/import", json={
        "company": "Example Corp", "title": "Backend Engineer",
        "url": "https://example.com/jobs/3", "jd_text": JD,
    })
    with respx.mock:
        respx.get(url__regex=r".*").mock(return_value=httpx.Response(404, text="no"))
        client.post("/pipeline/run", json={"resume_id": resume_id})
    app_id = client.get("/applications").json()["applications"][0]["id"]
    rejected = client.post(f"/applications/{app_id}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert client.post(f"/applications/{app_id}/applied").status_code == 409
