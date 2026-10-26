import httpx

from job_agent.agents.job_discovery import import_manual, persist_jobs
from job_agent.agents.orchestrator import StateMachineOrchestrator, get_orchestrator
from job_agent.agents.resume import ingest_resume
from job_agent.approval.gate import send_outreach_email, submit_application
from job_agent.config import Settings
from job_agent.db.models import ApplicationStatus as S
from job_agent.embeddings.fake import FakeEmbedder
from job_agent.storage.pipeline import InMemoryPipelineStore
from job_agent.storage.repository import InMemoryResumeRepository

GOOD_JD = (
    "Example Corp (fictional) — Backend Engineer\n"
    "Must have: Python, FastAPI, PostgreSQL, Docker.\n"
    "Nice to have: Kubernetes.\n"
)
BAD_JD = (
    "Other Co (fictional) — Research Engineer\n"
    "Must have: COBOL, Fortran, Haskell.\n"
)


def _offline():
    def handler(request):
        return httpx.Response(404, text="nope")
    return httpx.Client(transport=httpx.MockTransport(handler))


def _world(tmp_path, docx_bytes, jds):
    resumes = InMemoryResumeRepository()
    store = InMemoryPipelineStore(tmp_path / "runs.jsonl")
    embedder = FakeEmbedder(768)
    settings = Settings(
        database_url="", upload_dir=tmp_path / "up", run_log_path=tmp_path / "runs.jsonl",
        llm_judge="off",
    )
    ingest_resume(docx_bytes, "resume.docx", repository=resumes, embedder=embedder, upload_dir=settings.upload_dir)
    posts = []
    for i, jd in enumerate(jds):
        posts.append(import_manual(
            company="Example Corp", title=f"Role {i}",
            url=f"https://example.com/jobs/{i}", jd_text=jd,
        ))
    saved, errors = persist_jobs(store, embedder, posts)
    assert not errors
    resume_id = next(iter(resumes._versions))
    orch = StateMachineOrchestrator(
        store=store, resumes=resumes, embedder=embedder, settings=settings, client=_offline(),
    )
    return orch, store, resume_id, [job.job_id for job, _ in saved]


def test_happy_path_stops_at_approval(tmp_path, docx_bytes):
    orch, store, resume_id, ids = _world(tmp_path, docx_bytes, [GOOD_JD])
    result = orch.run(ids[0], resume_id)
    assert result.status == S.awaiting_approval, result.notes
    assert "awaiting_approval" in result.steps
    assert result.needs_human_review is False
    app = store.get_application_for_job(ids[0])
    assert app.approved_by_user is False
    assert app.metadata["eval_blocked"] is False
    assert "tailored_resume" in app.metadata
    contacts = store.list_contacts(ids[0])
    assert contacts and all(c.verified is False for c in contacts)

    # running it again does not move past the gate
    again = orch.run(ids[0], resume_id)
    assert again.status == S.awaiting_approval
    assert again.steps == ["skipped"]
    versions = orch.resumes.list_versions(resume_id)
    assert sum(1 for v in versions if (v.metadata or {}).get("kind") == "tailored") == 1


def test_approval_is_required_before_packet(tmp_path, docx_bytes):
    import pytest

    from job_agent.approval import ApprovalRequiredError

    orch, store, resume_id, ids = _world(tmp_path, docx_bytes, [GOOD_JD])
    orch.run(ids[0], resume_id)
    app = store.get_application_for_job(ids[0])
    with pytest.raises(ApprovalRequiredError):
        orch.resume_after_approval(app.id)
    view = {"status": app.status, "approved_by_user": app.approved_by_user, "metadata": app.metadata}
    from job_agent.approval import approve
    approve(view, approved_by="abinesh")
    app.status = view["status"]
    app.approved_by_user = True
    store.save_application(app)
    packet = orch.resume_after_approval(app.id)
    assert packet.status == S.approved
    assert "nothing was sent" in packet.notes[0]
    # still not applied, and the send/submit entry points still refuse to do it
    assert app.status == S.approved
    with pytest.raises(NotImplementedError):
        submit_application(view)
    with pytest.raises(NotImplementedError):
        send_outreach_email(view, to="r@example.com", subject="s", body="b")


def test_failed_gates_block_the_queue(tmp_path, docx_bytes):
    orch, store, resume_id, ids = _world(tmp_path, docx_bytes, [BAD_JD])
    result = orch.run(ids[0], resume_id)
    assert result.status == S.tailored
    assert result.needs_human_review is True
    assert "awaiting_approval" not in result.steps
    app = store.get_application_for_job(ids[0])
    assert app.metadata["eval_blocked"] is True
    assert app.approved_by_user is False


def test_one_bad_job_does_not_kill_the_batch(tmp_path, docx_bytes):
    orch, store, resume_id, ids = _world(tmp_path, docx_bytes, [GOOD_JD])
    import uuid
    missing = uuid.uuid4()
    results = orch.run_many([ids[0], missing], resume_id)
    assert len(results) == 2
    assert results[0].status == S.awaiting_approval
    assert results[1].needs_human_review is True
    assert store.list_runs()


def test_maf_adapter_delegates(tmp_path, docx_bytes):
    orch, store, resume_id, ids = _world(tmp_path, docx_bytes, [GOOD_JD])
    maf = get_orchestrator(
        "maf", store=store, resumes=orch.resumes, embedder=orch.embedder,
        settings=orch.settings, client=orch.client,
    )
    result = maf.run(ids[0], resume_id)
    assert result.status == S.awaiting_approval
    assert any("state machine" in note for note in result.notes)
    assert "tailor" in maf.tools()
