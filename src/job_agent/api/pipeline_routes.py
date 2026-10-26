"""Discovery, matching, drafts, approve / reject / mark applied."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from job_agent.agents.job_discovery import (
    discover_jobs,
    import_from_url,
    import_manual,
    persist_jobs,
)
from job_agent.agents.orchestrator import StateMachineOrchestrator
from job_agent.agents.tailoring import fallback_email
from job_agent.approval.gate import (
    ApprovalRequiredError,
    InvalidTransitionError,
    approve,
    transition,
)
from job_agent.checks import evaluate, extract_must_have
from job_agent.db.models import ApplicationStatus as S
from job_agent.errors import ApplyPilotError, HttpFailure, NotFound
from job_agent.exporting import write_resume_docx
from job_agent.net import _UA
from job_agent.records import BoardRef


class DiscoverIn(BaseModel):
    greenhouse: list[str] = Field(default_factory=list)
    lever: list[str] = Field(default_factory=list)
    ashby: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)


class ManualJobIn(BaseModel):
    company: str
    title: str
    url: str
    jd_text: str


class UrlJobIn(BaseModel):
    url: str
    company: str = ""
    title: str = ""


class RunIn(BaseModel):
    resume_id: uuid.UUID
    job_ids: list[uuid.UUID] | None = None


class ApproveIn(BaseModel):
    approved_by: str


class DraftIn(BaseModel):
    resume_text: str | None = None
    email_subject: str | None = None
    email_body: str | None = None


def _gate(app) -> dict:
    return {"status": app.status, "approved_by_user": app.approved_by_user, "metadata": app.metadata}


def _apply(app, view: dict) -> None:
    app.status = S(view["status"])
    app.approved_by_user = view["approved_by_user"] is True


def _status(app) -> str:
    return S(app.status).value


def _orch(request: Request) -> StateMachineOrchestrator:
    return StateMachineOrchestrator(
        store=request.app.state.store,
        resumes=request.app.state.repository,
        embedder=request.app.state.embedder,
        settings=request.app.state.settings,
    )


def _client(request: Request) -> httpx.Client:
    timeout = request.app.state.settings.http_timeout_s
    return httpx.Client(timeout=timeout, headers={"user-agent": _UA})


def _job_brief(store, job) -> dict:
    return {
        "job_id": job.job_id,
        "company": job.company,
        "title": job.title,
        "source": job.source,
        "url": job.url,
        "posted_at": job.posted_at,
    }


def _app_out(store, app) -> dict:
    job = store.get_job(app.job_id)
    meta = app.metadata or {}
    ev = meta.get("eval") or {}
    return {
        "id": app.id,
        "job_id": app.job_id,
        "company": job.company if job else "",
        "title": job.title if job else "",
        "source": job.source if job else "",
        "url": job.url if job else "",
        "status": _status(app),
        "approved_by_user": app.approved_by_user is True,
        "applied_at": app.applied_at,
        "match_score": meta.get("match_score"),
        "missing_skills": list(meta.get("missing_skills") or []),
        "eval_blocked": bool(meta.get("eval_blocked")),
        "eval_failures": list((ev or {}).get("failures") or []),
        "tailor_mode": meta.get("tailor_mode"),
    }


def _original_text(resumes, app) -> str:
    raw = (app.metadata or {}).get("source_version_id")
    if not raw:
        return ""
    version = resumes.get_version(uuid.UUID(str(raw)))
    if version is None:
        return ""
    chunks = resumes.get_chunks(version.resume_id, version.version)
    return "\n".join(c.text for c in chunks)


def _boom(exc: Exception) -> None:
    if isinstance(exc, NotFound):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, (ApprovalRequiredError, InvalidTransitionError)):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, HttpFailure):
        raise HTTPException(502, str(exc)) from exc
    if isinstance(exc, ApplyPilotError):
        raise HTTPException(502, str(exc)) from exc
    raise exc


def register_pipeline_routes(app: FastAPI) -> None:
    @app.post("/discovery")
    def run_discovery(body: DiscoverIn, request: Request) -> dict:
        boards = (
            [BoardRef("greenhouse", t) for t in body.greenhouse]
            + [BoardRef("lever", t) for t in body.lever]
            + [BoardRef("ashby", t) for t in body.ashby]
        )
        if not boards:
            raise HTTPException(400, "pass at least one greenhouse, lever, or ashby board")
        settings = request.app.state.settings
        client = _client(request)
        try:
            found = discover_jobs(
                boards, roles=body.roles, client=client,
                timeout=settings.http_timeout_s, retries=settings.http_retries,
            )
            saved, save_errors = persist_jobs(request.app.state.store, request.app.state.embedder, found.jobs)
        except Exception as exc:
            _boom(exc)
        finally:
            client.close()
        store = request.app.state.store
        for err in [*found.errors, *save_errors]:
            store.add_run(step="discover", ok=False, message=err)
        return {
            "saved": len(saved),
            "created": sum(1 for _, created in saved if created),
            "job_ids": [job.job_id for job, _ in saved],
            "errors": [*found.errors, *save_errors],
        }

    @app.post("/jobs/import", status_code=201)
    def post_manual(body: ManualJobIn, request: Request) -> dict:
        try:
            posting = import_manual(
                company=body.company, title=body.title, url=body.url, jd_text=body.jd_text,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        saved, errors = persist_jobs(request.app.state.store, request.app.state.embedder, [posting])
        if errors or not saved:
            raise HTTPException(502, errors[0] if errors else "could not store job")
        job, created = saved[0]
        return {**_job_brief(request.app.state.store, job), "created": created}

    @app.post("/jobs/import-url", status_code=201)
    def post_url(body: UrlJobIn, request: Request) -> dict:
        client = _client(request)
        try:
            posting = import_from_url(
                body.url, client=client, company=body.company, title=body.title,
                timeout=request.app.state.settings.http_timeout_s,
            )
            saved, errors = persist_jobs(request.app.state.store, request.app.state.embedder, [posting])
        except Exception as exc:
            _boom(exc)
        finally:
            client.close()
        if errors or not saved:
            raise HTTPException(502, errors[0] if errors else "could not store job")
        job, created = saved[0]
        return {**_job_brief(request.app.state.store, job), "created": created}

    @app.get("/jobs")
    def list_jobs(request: Request) -> dict:
        store = request.app.state.store
        jobs = []
        for job in store.list_jobs():
            app = store.get_application_for_job(job.job_id)
            jobs.append({
                **_job_brief(store, job),
                "status": _status(app) if app else None,
                "application_id": app.id if app else None,
            })
        return {"count": len(jobs), "jobs": jobs}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: uuid.UUID, request: Request) -> dict:
        job = request.app.state.store.get_job(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        contacts = request.app.state.store.list_contacts(job_id)
        return {
            **_job_brief(request.app.state.store, job),
            "jd_text": job.jd_text,
            "contacts": [
                {
                    "name": c.name, "title": c.title, "email": c.email,
                    "source": c.source, "verified": c.verified, "confidence": c.confidence,
                }
                for c in contacts
            ],
        }

    @app.post("/pipeline/run")
    def run_pipeline(body: RunIn, request: Request) -> dict:
        resumes = request.app.state.repository
        store = request.app.state.store
        if not resumes.resume_exists(body.resume_id):
            raise HTTPException(404, "resume not found")
        if body.job_ids:
            ids = list(body.job_ids)
        else:
            ids = [j.job_id for j in store.list_jobs()]
        orch = _orch(request)
        results = orch.run_many(ids, body.resume_id)
        return {
            "results": [
                {
                    "job_id": r.job_id,
                    "status": S(r.status).value,
                    "steps": r.steps,
                    "needs_human_review": r.needs_human_review,
                    "notes": r.notes,
                }
                for r in results
            ]
        }

    @app.get("/applications")
    def list_apps(request: Request) -> dict:
        store = request.app.state.store
        rows = [_app_out(store, app) for app in store.list_applications()]
        return {"count": len(rows), "applications": rows}

    @app.get("/applications/{app_id}")
    def get_app(app_id: uuid.UUID, request: Request) -> dict:
        app = request.app.state.store.get_application(app_id)
        if app is None:
            raise HTTPException(404, "application not found")
        return _app_out(request.app.state.store, app)

    @app.get("/applications/{app_id}/draft")
    def get_draft(app_id: uuid.UUID, request: Request) -> dict:
        store = request.app.state.store
        app = store.get_application(app_id)
        if app is None:
            raise HTTPException(404, "application not found")
        meta = app.metadata or {}
        if not meta.get("tailored_resume"):
            raise HTTPException(404, "no draft yet")
        contacts = store.list_contacts(app.job_id)
        return {
            "id": app.id,
            "status": _status(app),
            "resume_text": meta.get("tailored_resume") or "",
            "email_subject": meta.get("email_subject") or "",
            "email_body": meta.get("email_body") or "",
            "eval": meta.get("eval") or {},
            "eval_blocked": bool(meta.get("eval_blocked")),
            "tailor_mode": meta.get("tailor_mode"),
            "match_score": meta.get("match_score"),
            "missing_skills": list(meta.get("missing_skills") or []),
            "contacts": [
                {"name": c.name, "email": c.email, "source": c.source,
                 "verified": c.verified, "confidence": c.confidence}
                for c in contacts
            ],
        }

    @app.patch("/applications/{app_id}/draft")
    def edit_draft(app_id: uuid.UUID, body: DraftIn, request: Request) -> dict:
        store = request.app.state.store
        resumes = request.app.state.repository
        app = store.get_application(app_id)
        if app is None:
            raise HTTPException(404, "application not found")
        if S(app.status) in (S.approved, S.applied, S.rejected):
            raise HTTPException(409, f"can't edit a draft in status {S(app.status).value}")
        meta = app.metadata
        if not meta.get("tailored_resume"):
            raise HTTPException(404, "no draft yet")
        if body.resume_text is not None:
            meta["tailored_resume"] = body.resume_text
        if body.email_subject is not None:
            meta["email_subject"] = body.email_subject
        if body.email_body is not None:
            meta["email_body"] = body.email_body
        if not meta.get("email_subject") or not meta.get("email_body"):
            job = store.get_job(app.job_id)
            subject, email = fallback_email("there", job.company if job else "", job.title if job else "", meta["tailored_resume"])
            meta.setdefault("email_subject", subject)
            meta.setdefault("email_body", email)

        job = store.get_job(app.job_id)
        original = _original_text(resumes, app)
        terms = extract_must_have(job.jd_text if job else "")
        docx_path = meta.get("docx_path") or ""
        if meta.get("tailored_resume"):
            path = Path(docx_path) if docx_path else Path(request.app.state.settings.upload_dir) / f"{app.id}.docx"
            try:
                write_resume_docx(meta["tailored_resume"], path)
                meta["docx_path"] = str(path)
                docx_path = str(path)
            except Exception:
                docx_path = None
        report = evaluate(
            original=original or meta["tailored_resume"],
            tailored=meta["tailored_resume"],
            jd=job.jd_text if job else "",
            retrieved_chunks=list(meta.get("retrieved_chunks") or []),
            must_have=terms,
            docx_path=docx_path,
            llm_model=request.app.state.settings.llm_model,
        )
        meta["eval"] = report.as_dict()
        meta["eval_blocked"] = report.blocked
        meta["tailor_mode"] = meta.get("tailor_mode") or "edited"
        view = _gate(app)
        try:
            if report.blocked and S(view["status"]) == S.awaiting_approval:
                transition(view, S.tailored)
                _apply(app, view)
            elif not report.blocked and S(view["status"]) == S.tailored:
                transition(view, S.awaiting_approval)
                _apply(app, view)
        except (ApprovalRequiredError, InvalidTransitionError) as exc:
            raise HTTPException(409, str(exc)) from exc
        store.save_application(app)
        return get_draft(app_id, request)

    @app.post("/applications/{app_id}/approve")
    def do_approve(app_id: uuid.UUID, body: ApproveIn, request: Request) -> dict:
        store = request.app.state.store
        app = store.get_application(app_id)
        if app is None:
            raise HTTPException(404, "application not found")
        if app.metadata.get("eval_blocked"):
            raise HTTPException(409, "eval gates failed; fix the draft before approval")
        try:
            view = _gate(app)
            approve(view, approved_by=body.approved_by)
            _apply(app, view)
            store.save_application(app)
        except (ApprovalRequiredError, InvalidTransitionError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return _app_out(store, app)

    @app.post("/applications/{app_id}/reject")
    def do_reject(app_id: uuid.UUID, request: Request) -> dict:
        store = request.app.state.store
        app = store.get_application(app_id)
        if app is None:
            raise HTTPException(404, "application not found")
        try:
            view = _gate(app)
            transition(view, S.rejected)
            _apply(app, view)
            store.save_application(app)
        except (ApprovalRequiredError, InvalidTransitionError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return _app_out(store, app)

    @app.post("/applications/{app_id}/applied")
    def mark_applied(app_id: uuid.UUID, request: Request) -> dict:
        # this is the user saying they already submitted it. we don't submit for them.
        store = request.app.state.store
        app = store.get_application(app_id)
        if app is None:
            raise HTTPException(404, "application not found")
        try:
            view = _gate(app)
            transition(view, S.applied)
            _apply(app, view)
            app.applied_at = datetime.now(UTC)
            store.save_application(app)
        except (ApprovalRequiredError, InvalidTransitionError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return _app_out(store, app)

    @app.post("/applications/{app_id}/packet")
    def packet(app_id: uuid.UUID, request: Request) -> dict:
        try:
            result = _orch(request).resume_after_approval(app_id)
        except Exception as exc:
            _boom(exc)
        return {
            "job_id": result.job_id,
            "status": S(result.status).value,
            "notes": result.notes,
        }

    @app.get("/applications/{app_id}/docx")
    def download_docx(app_id: uuid.UUID, request: Request):
        app = request.app.state.store.get_application(app_id)
        if app is None:
            raise HTTPException(404, "application not found")
        meta = app.metadata or {}
        path = Path(meta.get("docx_path") or "")
        text = meta.get("tailored_resume") or ""
        if (not path or not path.exists()) and text:
            path = Path(request.app.state.settings.upload_dir) / f"{app.id}.docx"
            write_resume_docx(text, path)
            meta["docx_path"] = str(path)
            request.app.state.store.save_application(app)
        if not path or not path.exists():
            raise HTTPException(404, "no docx yet")
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=path.name,
        )

    @app.get("/runs")
    def list_runs(request: Request, limit: int = 50) -> dict:
        rows = request.app.state.store.list_runs(limit=min(limit, 200))
        return {
            "count": len(rows),
            "runs": [
                {
                    "id": r.id, "job_id": r.job_id, "resume_id": r.resume_id,
                    "step": r.step, "ok": r.ok, "message": r.message,
                    "detail": r.detail, "created_at": r.created_at,
                }
                for r in rows
            ],
        }
