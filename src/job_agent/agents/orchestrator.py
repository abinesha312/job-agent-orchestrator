"""Walk one job up to awaiting_approval. Never past it."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from job_agent.agents.email_finder import find_contacts, to_stored
from job_agent.agents.job_discovery import discover_jobs
from job_agent.agents.retrieval import score_match
from job_agent.agents.tailoring import tailor_resume
from job_agent.approval.gate import require_approval, transition
from job_agent.config import Settings, get_settings
from job_agent.db.models import ApplicationStatus
from job_agent.embeddings.factory import get_embedder
from job_agent.errors import NotFound
from job_agent.log import event
from job_agent.net import _UA


@dataclass
class RunResult:
    job_id: uuid.UUID
    status: ApplicationStatus
    steps: list[str] = field(default_factory=list)
    needs_human_review: bool = False
    notes: list[str] = field(default_factory=list)


def _gate(app) -> dict:
    return {
        "status": app.status,
        "approved_by_user": app.approved_by_user,
        "metadata": app.metadata,
    }


def _apply(app, view: dict) -> None:
    app.status = ApplicationStatus(view["status"])
    app.approved_by_user = view["approved_by_user"] is True


def _defaults(settings: Settings):
    from job_agent.storage.pipeline import InMemoryPipelineStore, SqlPipelineStore
    from job_agent.storage.repository import InMemoryResumeRepository, SqlResumeRepository

    if not settings.database_url:
        return InMemoryResumeRepository(), InMemoryPipelineStore(settings.run_log_path)
    from job_agent.db.session import make_engine, make_session_factory

    factory = make_session_factory(make_engine(settings.database_url))
    return SqlResumeRepository(factory), SqlPipelineStore(factory, settings.run_log_path)


class Orchestrator(ABC):
    max_steps: int = 20

    @abstractmethod
    def run(self, job_id: uuid.UUID, resume_id: uuid.UUID) -> RunResult:
        """Drive one job up to awaiting_approval. Never further."""

    @abstractmethod
    def resume_after_approval(self, application_id: uuid.UUID) -> RunResult:
        """Packet for the user. Does not submit and does not email."""


class StateMachineOrchestrator(Orchestrator):
    def __init__(self, store=None, resumes=None, embedder=None, settings: Settings | None = None,
                 client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self.embedder = embedder or get_embedder(self.settings)
        if resumes is None or store is None:
            default_resumes, default_store = _defaults(self.settings)
            resumes = resumes or default_resumes
            store = store or default_store
        self.resumes = resumes
        self.store = store
        self.client = client

    def run_many(self, job_ids: list[uuid.UUID], resume_id: uuid.UUID) -> list[RunResult]:
        results = []
        for job_id in job_ids:
            # run() already swallows per-job errors; this is a second net
            try:
                results.append(self.run(job_id, resume_id))
            except Exception as exc:
                event("orchestrator", ok=False, job_id=str(job_id), error=str(exc)[:300])
                results.append(RunResult(
                    job_id, ApplicationStatus.discovered, steps=["failed"],
                    needs_human_review=True, notes=[str(exc)],
                ))
        return results

    def run(self, job_id: uuid.UUID, resume_id: uuid.UUID) -> RunResult:
        try:
            return self._run(job_id, resume_id)
        except Exception as exc:
            event("orchestrator", ok=False, job_id=str(job_id), error=str(exc)[:400])
            try:
                self.store.add_run(
                    step="orchestrator", ok=False, message=str(exc), job_id=job_id, resume_id=resume_id,
                )
            except Exception:
                pass
            status = ApplicationStatus.discovered
            try:
                app = self.store.get_application_for_job(job_id)
                if app:
                    status = ApplicationStatus(app.status)
            except Exception:
                pass
            return RunResult(job_id, status, steps=["failed"], needs_human_review=True, notes=[str(exc)])

    def _client(self) -> httpx.Client:
        if self.client is not None:
            return self.client
        return httpx.Client(timeout=self.settings.http_timeout_s, headers={"user-agent": _UA})

    def _run(self, job_id: uuid.UUID, resume_id: uuid.UUID) -> RunResult:
        job = self.store.get_job(job_id)
        if job is None:
            raise NotFound(f"unknown job {job_id}")
        if not self.resumes.resume_exists(resume_id):
            raise NotFound(f"unknown resume {resume_id}")

        app = self.store.get_or_create_application(job_id)
        if app.status in (
            ApplicationStatus.awaiting_approval,
            ApplicationStatus.approved,
            ApplicationStatus.applied,
            ApplicationStatus.rejected,
        ):
            self.store.add_run(
                step="orchestrator", ok=True, message=f"left at {ApplicationStatus(app.status).value}",
                job_id=job_id, resume_id=resume_id,
            )
            return RunResult(
                job_id, ApplicationStatus(app.status), steps=["skipped"],
                notes=[f"already {ApplicationStatus(app.status).value}"],
            )

        steps: list[str] = []
        notes: list[str] = []
        if len(steps) > self.max_steps:
            raise RuntimeError("step limit")

        match = score_match(
            job_id, None, store=self.store, resumes=self.resumes, embedder=self.embedder,
            resume_id=resume_id, k=self.settings.retrieval_k,
        )
        steps.append("matched")
        view = _gate(app)
        if ApplicationStatus(view["status"]) == ApplicationStatus.discovered:
            transition(view, ApplicationStatus.matched)
            _apply(app, view)
        app.metadata["match_score"] = match.match_score
        app.metadata["missing_skills"] = match.missing_skills
        app.metadata["retrieved_chunks"] = [c.text for c in match.chunks]
        self.store.save_application(app)

        owns_client = self.client is None
        client = self._client()
        try:
            found = find_contacts(job, client=client, timeout=min(8, self.settings.http_timeout_s), retries=1)
            self.store.replace_contacts(job.job_id, to_stored(job.job_id, found))
            steps.append("contacts")
            notes.append(f"{len(found)} contacts, none verified")
        except Exception as exc:
            notes.append(f"contacts skipped: {exc}")
            self.store.add_run(
                step="contacts", ok=False, message=str(exc), job_id=job_id, resume_id=resume_id,
            )
        finally:
            if owns_client:
                client.close()

        if len(steps) > self.max_steps:
            raise RuntimeError("step limit")

        tailored = tailor_resume(
            match.resume_version_id, job_id, resumes=self.resumes, store=self.store,
            embedder=self.embedder, upload_dir=self.settings.upload_dir, settings=self.settings,
            k=self.settings.retrieval_k,
        )
        steps.append("tailored")
        view = _gate(app)
        if ApplicationStatus(view["status"]) == ApplicationStatus.matched:
            transition(view, ApplicationStatus.tailored)
            _apply(app, view)
        app.metadata.update({
            "tailored_resume": tailored.resume_text,
            "email_subject": tailored.email_subject,
            "email_body": tailored.email_body,
            "docx_path": tailored.docx_path,
            "version_id": str(tailored.version_id),
            "eval": tailored.report,
            "eval_blocked": tailored.blocked,
            "tailor_mode": tailored.mode,
            "source_version_id": str(match.resume_version_id),
            "match_score": match.match_score,
            "missing_skills": match.missing_skills,
        })
        if tailored.blocked:
            notes.append("blocked by eval: " + ", ".join(tailored.failures))
        else:
            view = _gate(app)
            if ApplicationStatus(view["status"]) == ApplicationStatus.tailored:
                transition(view, ApplicationStatus.awaiting_approval)
                _apply(app, view)
            steps.append("awaiting_approval")
        self.store.save_application(app)
        self.store.add_run(
            step="orchestrator", ok=not tailored.blocked, message="; ".join(notes) or "ok",
            detail={"steps": steps, "failures": tailored.failures},
            job_id=job_id, resume_id=resume_id,
        )
        return RunResult(
            job_id, ApplicationStatus(app.status), steps=steps,
            needs_human_review=tailored.blocked, notes=notes,
        )

    def resume_after_approval(self, application_id: uuid.UUID) -> RunResult:
        app = self.store.get_application(application_id)
        if app is None:
            raise NotFound(f"unknown application {application_id}")
        require_approval(_gate(app))
        return RunResult(
            app.job_id, ApplicationStatus(app.status), steps=["packet"],
            notes=["packet is ready for you to submit yourself. nothing was sent."],
        )

    def tools(self) -> dict:
        # plain callables a framework can register. the state machine calls them directly.
        return {
            "discover": discover_jobs,
            "score_match": score_match,
            "tailor": tailor_resume,
            "find_contacts": find_contacts,
        }


class MicrosoftAgentFrameworkOrchestrator(Orchestrator):
    """Same steps as the state machine. MAF can wrap tools() if you install it later."""

    def __init__(self, inner: StateMachineOrchestrator | None = None, **kwargs) -> None:
        self.inner = inner or StateMachineOrchestrator(**kwargs)

    def tools(self) -> dict:
        return self.inner.tools()

    def run(self, job_id: uuid.UUID, resume_id: uuid.UUID) -> RunResult:
        result = self.inner.run(job_id, resume_id)
        note = "maf adapter delegated to the state machine"
        try:
            import importlib
            importlib.import_module("agent_framework")
            note = "agent-framework is installed; tools() exposes the steps, run used the state machine"
        except Exception:
            pass
        result.notes = [*result.notes, note]
        return result

    def resume_after_approval(self, application_id: uuid.UUID) -> RunResult:
        return self.inner.resume_after_approval(application_id)


class AutoGenOrchestrator(Orchestrator):
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def run(self, job_id: uuid.UUID, resume_id: uuid.UUID) -> RunResult:
        raise NotImplementedError("autogen is archived, use state_machine")

    def resume_after_approval(self, application_id: uuid.UUID) -> RunResult:
        raise NotImplementedError("autogen is archived, use state_machine")


_REGISTRY: dict[str, type[Orchestrator]] = {
    "state_machine": StateMachineOrchestrator,
    "maf": MicrosoftAgentFrameworkOrchestrator,
    "autogen": AutoGenOrchestrator,
}


def get_orchestrator(kind: str = "state_machine", **kwargs) -> Orchestrator:
    try:
        cls = _REGISTRY[kind]
    except KeyError as exc:
        raise ValueError(f"unknown orchestrator {kind!r}; choose from {sorted(_REGISTRY)}") from exc
    return cls(**kwargs)

