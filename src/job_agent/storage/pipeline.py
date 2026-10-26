"""Jobs, matches, applications, contacts, run log. Memory or Postgres."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from job_agent.db.models import Application, ApplicationStatus, Contact, Job, Match, RunLog
from job_agent.log import get_logger
from job_agent.records import (
    JobPosting,
    RunEvent,
    StoredApplication,
    StoredContact,
    StoredJob,
    StoredMatch,
)
from job_agent.text import clip, normalize_url


def _now() -> datetime:
    return datetime.now(UTC)


def _status(value) -> ApplicationStatus:
    if isinstance(value, ApplicationStatus):
        return value
    return ApplicationStatus(str(value))


class InMemoryPipelineStore:
    def __init__(self, run_log_path: Path | None = None) -> None:
        self.jobs: dict[uuid.UUID, StoredJob] = {}
        self.by_url: dict[str, uuid.UUID] = {}
        self.matches: dict[tuple[uuid.UUID, uuid.UUID], StoredMatch] = {}
        self.apps: dict[uuid.UUID, StoredApplication] = {}
        self.apps_by_job: dict[uuid.UUID, uuid.UUID] = {}
        self.contacts: dict[uuid.UUID, list[StoredContact]] = {}
        self.runs: list[RunEvent] = []
        self.run_log_path = Path(run_log_path) if run_log_path else None
        self._lock = threading.Lock()

    def upsert_job(self, posting: JobPosting, embedding: list[float] | None = None) -> tuple[StoredJob, bool]:
        url = normalize_url(posting.url)
        with self._lock:
            existing_id = self.by_url.get(url)
            if existing_id:
                job = self.jobs[existing_id]
                job.jd_text = posting.jd_text
                job.title = clip(posting.title, 255)
                job.company = clip(posting.company, 255)
                job.metadata = {**job.metadata, **posting.metadata}
                if embedding is not None:
                    job.jd_embedding = embedding
                return job, False
            job = StoredJob(
                job_id=uuid.uuid4(),
                company=clip(posting.company, 255) or "Unknown",
                title=clip(posting.title, 255) or "Untitled",
                source=clip(posting.source, 32) or "manual",
                url=url,
                jd_text=posting.jd_text,
                posted_at=posting.posted_at,
                metadata=dict(posting.metadata),
                created_at=_now(),
                jd_embedding=embedding,
            )
            self.jobs[job.job_id] = job
            self.by_url[url] = job.job_id
            return job, True

    def update_job_embedding(self, job_id: uuid.UUID, embedding: list[float]) -> None:
        job = self.jobs.get(job_id)
        if job:
            job.jd_embedding = embedding

    def get_job(self, job_id: uuid.UUID) -> StoredJob | None:
        return self.jobs.get(job_id)

    def list_jobs(self) -> list[StoredJob]:
        return sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)

    def upsert_match(self, *, job_id, resume_version, match_score, missing_skills, metadata) -> StoredMatch:
        key = (job_id, resume_version)
        with self._lock:
            current = self.matches.get(key)
            if current:
                current.match_score = match_score
                current.missing_skills = list(missing_skills)
                current.metadata = dict(metadata)
                return current
            row = StoredMatch(
                uuid.uuid4(), job_id, resume_version, float(match_score),
                list(missing_skills), dict(metadata), _now(),
            )
            self.matches[key] = row
            return row

    def list_matches(self, *, job_id=None, resume_version=None) -> list[StoredMatch]:
        rows = list(self.matches.values())
        if job_id:
            rows = [r for r in rows if r.job_id == job_id]
        if resume_version:
            rows = [r for r in rows if r.resume_version == resume_version]
        return rows

    def get_or_create_application(self, job_id: uuid.UUID) -> StoredApplication:
        with self._lock:
            existing = self.apps_by_job.get(job_id)
            if existing:
                return self.apps[existing]
            app = StoredApplication(
                uuid.uuid4(), job_id, ApplicationStatus.discovered, False, None, {}, _now(),
            )
            self.apps[app.id] = app
            self.apps_by_job[job_id] = app.id
            return app

    def get_application(self, app_id: uuid.UUID) -> StoredApplication | None:
        return self.apps.get(app_id)

    def get_application_for_job(self, job_id: uuid.UUID) -> StoredApplication | None:
        app_id = self.apps_by_job.get(job_id)
        return self.apps.get(app_id) if app_id else None

    def save_application(self, app: StoredApplication) -> StoredApplication:
        with self._lock:
            app.status = _status(app.status)
            self.apps[app.id] = app
            self.apps_by_job[app.job_id] = app.id
            return app

    def list_applications(self) -> list[StoredApplication]:
        return sorted(self.apps.values(), key=lambda a: a.created_at, reverse=True)

    def replace_contacts(self, job_id: uuid.UUID, contacts: list[StoredContact]) -> None:
        with self._lock:
            self.contacts[job_id] = list(contacts)

    def list_contacts(self, job_id: uuid.UUID) -> list[StoredContact]:
        return list(self.contacts.get(job_id, []))

    def add_run(self, *, step: str, ok: bool = True, message: str = "", detail: dict | None = None,
                job_id: uuid.UUID | None = None, resume_id: uuid.UUID | None = None) -> RunEvent:
        ev = RunEvent(uuid.uuid4(), job_id, resume_id, step, ok, message, dict(detail or {}), _now())
        with self._lock:
            self.runs.append(ev)
        _append_file(self.run_log_path, ev)
        return ev

    def list_runs(self, limit: int = 100) -> list[RunEvent]:
        return list(reversed(self.runs[-limit:]))


class SqlPipelineStore:
    def __init__(self, session_factory: sessionmaker, run_log_path: Path | None = None) -> None:
        self._sf = session_factory
        self.run_log_path = Path(run_log_path) if run_log_path else None

    def upsert_job(self, posting: JobPosting, embedding: list[float] | None = None) -> tuple[StoredJob, bool]:
        url = normalize_url(posting.url)
        with self._sf.begin() as s:
            row = s.scalar(select(Job).where(Job.url == url))
            if row:
                row.jd_text = posting.jd_text
                row.title = clip(posting.title, 255) or row.title
                row.company = clip(posting.company, 255) or row.company
                row.meta = {**(row.meta or {}), **posting.metadata}
                if embedding is not None:
                    row.jd_embedding = embedding
                s.flush()
                return _job(row), False
            row = Job(
                company=clip(posting.company, 255) or "Unknown",
                title=clip(posting.title, 255) or "Untitled",
                source=clip(posting.source, 32) or "manual",
                url=url,
                jd_text=posting.jd_text,
                jd_embedding=embedding,
                posted_at=posting.posted_at,
                meta=dict(posting.metadata),
            )
            s.add(row)
            s.flush()
            return _job(row), True

    def update_job_embedding(self, job_id: uuid.UUID, embedding: list[float]) -> None:
        with self._sf.begin() as s:
            row = s.get(Job, job_id)
            if row:
                row.jd_embedding = embedding

    def get_job(self, job_id: uuid.UUID) -> StoredJob | None:
        with self._sf() as s:
            row = s.get(Job, job_id)
            return _job(row) if row else None

    def list_jobs(self) -> list[StoredJob]:
        with self._sf() as s:
            rows = s.scalars(select(Job).order_by(Job.created_at.desc())).all()
            return [_job(r) for r in rows]

    def upsert_match(self, *, job_id, resume_version, match_score, missing_skills, metadata) -> StoredMatch:
        with self._sf.begin() as s:
            row = s.scalar(
                select(Match).where(Match.job_id == job_id, Match.resume_version == resume_version)
            )
            if row:
                row.match_score = float(match_score)
                row.missing_skills = list(missing_skills)
                row.meta = dict(metadata)
            else:
                row = Match(
                    job_id=job_id, resume_version=resume_version, match_score=float(match_score),
                    missing_skills=list(missing_skills), meta=dict(metadata),
                )
                s.add(row)
            s.flush()
            s.refresh(row)
            return _match(row)

    def list_matches(self, *, job_id=None, resume_version=None) -> list[StoredMatch]:
        with self._sf() as s:
            stmt = select(Match)
            if job_id:
                stmt = stmt.where(Match.job_id == job_id)
            if resume_version:
                stmt = stmt.where(Match.resume_version == resume_version)
            return [_match(r) for r in s.scalars(stmt).all()]

    def get_or_create_application(self, job_id: uuid.UUID) -> StoredApplication:
        with self._sf.begin() as s:
            row = s.scalar(
                select(Application).where(Application.job_id == job_id).order_by(Application.created_at.desc())
            )
            if row:
                return _app(row)
            row = Application(job_id=job_id, status=ApplicationStatus.discovered, approved_by_user=False, meta={})
            s.add(row)
            s.flush()
            s.refresh(row)
            return _app(row)

    def get_application(self, app_id: uuid.UUID) -> StoredApplication | None:
        with self._sf() as s:
            row = s.get(Application, app_id)
            return _app(row) if row else None

    def get_application_for_job(self, job_id: uuid.UUID) -> StoredApplication | None:
        with self._sf() as s:
            row = s.scalar(
                select(Application).where(Application.job_id == job_id).order_by(Application.created_at.desc())
            )
            return _app(row) if row else None

    def save_application(self, app: StoredApplication) -> StoredApplication:
        with self._sf.begin() as s:
            row = s.get(Application, app.id)
            status = _status(app.status)
            if row is None:
                row = Application(
                    id=app.id, job_id=app.job_id, status=status,
                    approved_by_user=bool(app.approved_by_user), applied_at=app.applied_at,
                    meta=dict(app.metadata or {}),
                )
                s.add(row)
            else:
                row.status = status
                row.approved_by_user = bool(app.approved_by_user)
                row.applied_at = app.applied_at
                row.meta = dict(app.metadata or {})
            s.flush()
            s.refresh(row)
            return _app(row)

    def list_applications(self) -> list[StoredApplication]:
        with self._sf() as s:
            rows = s.scalars(select(Application).order_by(Application.created_at.desc())).all()
            return [_app(r) for r in rows]

    def replace_contacts(self, job_id: uuid.UUID, contacts: list[StoredContact]) -> None:
        with self._sf.begin() as s:
            s.execute(delete(Contact).where(Contact.job_id == job_id))
            for c in contacts:
                s.add(Contact(
                    id=c.id, job_id=job_id, name=clip(c.name, 255) or "Unknown",
                    title=clip(c.title or "", 255) or None,
                    email=(c.email or None),
                    source=clip(c.source, 32) or "pattern_guess",
                    verified=bool(c.verified),
                    meta={**(c.metadata or {}), "confidence": c.confidence},
                ))

    def list_contacts(self, job_id: uuid.UUID) -> list[StoredContact]:
        with self._sf() as s:
            rows = s.scalars(select(Contact).where(Contact.job_id == job_id)).all()
            return [_contact(r) for r in rows]

    def add_run(self, *, step: str, ok: bool = True, message: str = "", detail: dict | None = None,
                job_id: uuid.UUID | None = None, resume_id: uuid.UUID | None = None) -> RunEvent:
        with self._sf.begin() as s:
            row = RunLog(
                job_id=job_id, resume_id=resume_id, step=clip(step, 64) or "run",
                ok=ok, message=message or "", meta=dict(detail or {}),
            )
            s.add(row)
            s.flush()
            s.refresh(row)
            ev = _run(row)
        _append_file(self.run_log_path, ev)
        return ev

    def list_runs(self, limit: int = 100) -> list[RunEvent]:
        with self._sf() as s:
            rows = s.scalars(select(RunLog).order_by(RunLog.created_at.desc()).limit(limit)).all()
            return [_run(r) for r in rows]


def _append_file(path: Path | None, ev: RunEvent) -> None:
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "id": str(ev.id),
            "job_id": str(ev.job_id) if ev.job_id else None,
            "resume_id": str(ev.resume_id) if ev.resume_id else None,
            "step": ev.step,
            "ok": ev.ok,
            "message": ev.message,
            "detail": ev.detail,
            "at": ev.created_at.isoformat(),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        get_logger().warning("run log file write failed", extra={"fields": {"step": "run_log"}})


def _vec(value) -> list[float] | None:
    if value is None:
        return None
    return list(value)


def _job(row: Job) -> StoredJob:
    return StoredJob(
        row.job_id, row.company, row.title, row.source, row.url, row.jd_text, row.posted_at,
        dict(row.meta or {}), row.created_at, _vec(row.jd_embedding),
    )


def _match(row: Match) -> StoredMatch:
    return StoredMatch(
        row.id, row.job_id, row.resume_version, float(row.match_score),
        list(row.missing_skills or []), dict(row.meta or {}), row.created_at,
    )


def _app(row: Application) -> StoredApplication:
    return StoredApplication(
        row.id, row.job_id, _status(row.status), bool(row.approved_by_user), row.applied_at,
        dict(row.meta or {}), row.created_at,
    )


def _contact(row: Contact) -> StoredContact:
    meta = dict(row.meta or {})
    return StoredContact(
        row.id, row.job_id, row.name, row.title, row.email, row.source, bool(row.verified),
        float(meta.get("confidence") or 0.0), meta, row.created_at,
    )


def _run(row: RunLog) -> RunEvent:
    return RunEvent(
        row.id, row.job_id, row.resume_id, row.step, bool(row.ok), row.message or "",
        dict(row.meta or {}), row.created_at,
    )
