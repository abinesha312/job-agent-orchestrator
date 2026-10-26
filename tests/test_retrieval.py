from pathlib import Path

from job_agent.agents.job_discovery import import_manual, persist_jobs
from job_agent.agents.resume import ingest_resume
from job_agent.agents.retrieval import score_match
from job_agent.embeddings.fake import FakeEmbedder
from job_agent.storage.pipeline import InMemoryPipelineStore
from job_agent.storage.repository import InMemoryResumeRepository

FIXTURE = Path(__file__).parent / "fixtures" / "sample_resume.txt"
JD = (
    "Example Corp (fictional) — Backend Engineer\n"
    "Must have: Python, FastAPI, PostgreSQL, Docker, COBOL.\n"
)


def test_scores_and_records_missing_skill(tmp_path, docx_bytes):
    resumes = InMemoryResumeRepository()
    store = InMemoryPipelineStore()
    embedder = FakeEmbedder(768)
    ingest_resume(
        docx_bytes, "resume.docx", repository=resumes, embedder=embedder,
        upload_dir=tmp_path, max_chars=800,
    )
    # the text fixture is what the docx was built from
    assert "Python" in FIXTURE.read_text()
    post = import_manual(
        company="Example Corp", title="Backend Engineer",
        url="https://example.com/jobs/1", jd_text=JD,
    )
    saved, errors = persist_jobs(store, embedder, [post])
    assert not errors
    job = saved[0][0]
    resume_id = next(iter(resumes._versions))
    result = score_match(job.job_id, None, store=store, resumes=resumes, embedder=embedder, resume_id=resume_id)
    assert result.chunks
    assert result.chunks[0].section in {"skills", "experience", "summary"}
    assert result.match_score > 0
    assert "COBOL" in result.missing_skills or "cobol" in [s.lower() for s in result.missing_skills]
    assert not any(s.lower() == "python" for s in result.missing_skills)
    matches = store.list_matches(job_id=job.job_id)
    assert len(matches) == 1
    assert matches[0].match_score == result.match_score
