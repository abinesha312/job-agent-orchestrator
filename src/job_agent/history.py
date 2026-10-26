"""Application history imported from an export file.

The export is a small relational document: companies, jobs, resumes, applications and
events, linked by ids. It is saved to disk as one JSON file and joined on read.
"""

from __future__ import annotations

import json
import threading
from collections import Counter
from pathlib import Path

REQUIRED = ("companies", "jobs", "resumes", "applications", "events")


class HistoryError(ValueError):
    pass


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._doc: dict | None = None
        self._index: dict = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self._set(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, HistoryError):
            self._doc = None

    def _set(self, doc: dict) -> None:
        if not isinstance(doc, dict):
            raise HistoryError("export must be a JSON object")
        missing = [k for k in REQUIRED if not isinstance(doc.get(k), list)]
        if missing:
            raise HistoryError("export is missing: " + ", ".join(missing))
        events: dict[str, list] = {}
        for e in doc["events"]:
            events.setdefault(e.get("application_id"), []).append(e)
        for rows in events.values():
            rows.sort(key=lambda e: e.get("date") or "")
        self._index = {
            "company": {c["company_id"]: c for c in doc["companies"]},
            "job": {j["job_id"]: j for j in doc["jobs"]},
            "resume": {r["resume_id"]: r for r in doc["resumes"]},
            "app": {a["application_id"]: a for a in doc["applications"]},
            "events": events,
        }
        self._doc = doc

    def import_doc(self, doc: dict) -> dict:
        with self._lock:
            self._set(doc)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return self.summary()

    @property
    def loaded(self) -> bool:
        return self._doc is not None

    def _row(self, a: dict) -> dict:
        job = self._index["job"].get(a.get("job_id"), {})
        company = self._index["company"].get(job.get("company_id"), {})
        resume = self._index["resume"].get(a.get("resume_id"), {})
        events = self._index["events"].get(a["application_id"], [])
        outcome = next((e["type"] for e in reversed(events) if e.get("type") in ("rejection", "interview")), None)
        return {
            "application_id": a["application_id"],
            "status": a.get("status"),
            "applied_at": a.get("applied_at"),
            "submitted_by_bot": a.get("submitted_by_bot"),
            "notes": a.get("notes"),
            "company_id": company.get("company_id"),
            "company": company.get("name") or job.get("company_id"),
            "job_id": a.get("job_id"),
            "req_id": job.get("req_id"),
            "title": job.get("title"),
            "location": job.get("location"),
            "url": job.get("url"),
            "resume_id": a.get("resume_id"),
            "resume_version": resume.get("version"),
            "event_count": len(events),
            "outcome": outcome,
        }

    def summary(self) -> dict:
        if not self._doc:
            return {"loaded": False}
        apps = self._doc["applications"]
        by_company: Counter = Counter()
        for a in apps:
            job = self._index["job"].get(a.get("job_id"), {})
            c = self._index["company"].get(job.get("company_id"), {})
            by_company[c.get("name") or job.get("company_id") or "unknown"] += 1
        return {
            "loaded": True,
            "generated_at": self._doc.get("generated_at"),
            "timezone_note": self._doc.get("timezone_note"),
            "status_definitions": self._doc.get("status_definitions", {}),
            "totals": {
                "applications": len(apps), "jobs": len(self._doc["jobs"]),
                "companies": len(self._doc["companies"]), "resumes": len(self._doc["resumes"]),
                "events": len(self._doc["events"]),
            },
            "by_status": dict(Counter(a.get("status") for a in apps)),
            "by_company": dict(by_company.most_common()),
            "by_event": dict(Counter(e.get("type") for e in self._doc["events"])),
            "companies": self._doc["companies"],
        }

    def applications(self, *, company: str | None = None, status: str | None = None,
                     q: str | None = None, offset: int = 0, limit: int = 50) -> dict:
        if not self._doc:
            return {"total": 0, "rows": []}
        rows = [self._row(a) for a in self._doc["applications"]]
        if company:
            rows = [r for r in rows if r["company_id"] == company or r["company"] == company]
        if status:
            rows = [r for r in rows if r["status"] == status]
        if q:
            needle = q.lower()
            rows = [r for r in rows if needle in " ".join(
                str(r.get(k) or "") for k in ("title", "company", "req_id", "resume_id", "location", "notes")).lower()]
        rows.sort(key=lambda r: r["applied_at"] or "", reverse=True)
        return {"total": len(rows), "rows": rows[offset:offset + limit]}

    def detail(self, application_id: str) -> dict | None:
        a = self._index.get("app", {}).get(application_id) if self._doc else None
        if a is None:
            return None
        resume = self._index["resume"].get(a.get("resume_id"), {})
        return {
            **self._row(a),
            "confirmation_source": a.get("confirmation_source"),
            "resume": resume,
            "events": self._index["events"].get(application_id, []),
        }
