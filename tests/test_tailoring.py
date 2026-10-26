from pathlib import Path

from job_agent.agents.job_discovery import import_manual, persist_jobs
from job_agent.agents.resume import ingest_resume
from job_agent.agents.tailoring import fallback_resume, tailor_resume
from job_agent.checks import faithfulness
from job_agent.embeddings.fake import FakeEmbedder
from job_agent.storage.pipeline import InMemoryPipelineStore
from job_agent.storage.repository import InMemoryResumeRepository

JD = (
    "Example Corp (fictional) — Backend Engineer\n"
    "Must have: Python, FastAPI, PostgreSQL, Docker.\n"
    "Nice to have: Kubernetes.\n"
)


def _setup(tmp_path, docx_bytes):
    resumes = InMemoryResumeRepository()
    store = InMemoryPipelineStore()
    embedder = FakeEmbedder(768)
    ingest_resume(docx_bytes, "resume.docx", repository=resumes, embedder=embedder, upload_dir=tmp_path)
    post = import_manual(
        company="Example Corp", title="Backend Engineer",
        url="https://example.com/jobs/backend", jd_text=JD,
    )
    saved, errors = persist_jobs(store, embedder, [post])
    assert not errors
    job = saved[0][0]
    resume_id = next(iter(resumes._versions))
    return resumes, store, embedder, job, resume_id


def test_fallback_does_not_invent(docx_bytes, tmp_path):
    resumes, store, embedder, job, resume_id = _setup(tmp_path, docx_bytes)
    result = tailor_resume(
        None, job.job_id, resumes=resumes, store=store, embedder=embedder,
        upload_dir=tmp_path, resume_id=resume_id,
    )
    chunks = resumes.get_chunks(resume_id, 1)
    source = "\n".join(c.text for c in chunks)
    score, detail = faithfulness(source, result.resume_text)
    assert score == 1.0, detail
    assert "Rust" not in result.resume_text
    assert Path(result.docx_path).exists()
    assert result.docx_path.endswith(".docx")
    assert not result.blocked, result.failures
    assert result.mode == "fallback"
    # second call reuses the version
    again = tailor_resume(
        None, job.job_id, resumes=resumes, store=store, embedder=embedder,
        upload_dir=tmp_path, resume_id=resume_id,
    )
    assert again.reused
    assert again.version_id == result.version_id


def test_invented_skill_fails_faithfulness():
    original = "SKILLS\nPython, Docker\n"
    tailored = original + "SKILLS\nRust, Kubernetes\n"
    score, detail = faithfulness(original, tailored)
    assert score == 0.0
    assert "rust" in detail


def test_fallback_resume_keeps_real_bullets():
    text = Path(__file__).parent.joinpath("fixtures/sample_resume.txt").read_text()
    out = fallback_resume(text, ["Python", "FastAPI", "PostgreSQL", "Docker"])
    assert "FastAPI" in out
    assert "Acme Widgets" in out
    assert "Rust" not in out
