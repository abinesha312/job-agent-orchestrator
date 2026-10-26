from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from job_agent.api.app import create_app
from job_agent.config import Settings
from job_agent.embeddings import FakeEmbedder
from job_agent.storage import InMemoryResumeRepository

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_url="", upload_dir=tmp_path / "uploads", max_upload_mb=1)
    app = create_app(settings=settings, repository=InMemoryResumeRepository(),
                     embedder=FakeEmbedder(dim=768))
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0", "storage": "memory", "embedder": "fake-hash"}


def test_upload_pdf_then_get_chunks(client, pdf_bytes, tmp_path):
    r = client.post("/resumes", files={"file": ("resume.pdf", pdf_bytes, "application/pdf")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1 and body["chunk_count"] > 0
    assert body["sections"][:3] == ["header", "summary", "experience"]
    rid = body["resume_id"]
    assert (tmp_path / "uploads" / rid / "v1_resume.pdf").exists()

    r = client.get(f"/resumes/{rid}/chunks")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == body["chunk_count"]
    for i, c in enumerate(data["chunks"]):
        assert c["order"] == i
        assert c["metadata"]["resume_id"] == rid
        assert c["metadata"]["version"] == 1
        assert c["metadata"]["section"] == c["section"]
        assert c["metadata"]["embedding_model"] == "fake-hash"
        assert c["embedding_dim"] == 768 and c["embedding"] is None


def test_upload_docx_new_version_and_filters(client, docx_bytes, pdf_bytes):
    rid = client.post("/resumes", files={"file": ("cv.pdf", pdf_bytes, "application/pdf")}).json()["resume_id"]
    r = client.post("/resumes", files={"file": ("cv.docx", docx_bytes, DOCX_MIME)}, data={"resume_id": rid})
    assert r.status_code == 201 and r.json()["version"] == 2

    latest = client.get(f"/resumes/{rid}/chunks").json()
    assert latest["version"] == 2
    v1 = client.get(f"/resumes/{rid}/chunks", params={"version": 1}).json()
    assert v1["version"] == 1 and all(c["metadata"]["file_type"] == "pdf" for c in v1["chunks"])

    skills = client.get(f"/resumes/{rid}/chunks", params={"section": "skills", "include_embeddings": True}).json()
    assert skills["count"] >= 1 and all(c["section"] == "skills" for c in skills["chunks"])
    assert len(skills["chunks"][0]["embedding"]) == 768


def test_upload_errors(client):
    assert client.post("/resumes", files={"file": ("a.txt", b"hi", "text/plain")}).status_code == 415
    assert client.post("/resumes", files={"file": ("a.pdf", b"garbage", "application/pdf")}).status_code == 422
    big = b"0" * (1024 * 1024 + 10)
    assert client.post("/resumes", files={"file": ("a.pdf", big, "application/pdf")}).status_code == 413
    missing = str(uuid.uuid4())
    r = client.post("/resumes", files={"file": ("a.pdf", b"x", "application/pdf")}, data={"resume_id": missing})
    assert r.status_code == 404


def test_chunks_404s(client, pdf_bytes):
    assert client.get(f"/resumes/{uuid.uuid4()}/chunks").status_code == 404
    rid = client.post("/resumes", files={"file": ("r.pdf", pdf_bytes, "application/pdf")}).json()["resume_id"]
    assert client.get(f"/resumes/{rid}/chunks", params={"version": 9}).status_code == 404
    assert client.get("/resumes/not-a-uuid/chunks").status_code == 422
