"""Company career search: AMD, Apple, Microsoft, Amazon, OpenAI, Anthropic."""

from __future__ import annotations

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from job_agent.agents.company_sources import BY_ID, COMPANIES, search_companies
from job_agent.agents.job_discovery import persist_jobs
from job_agent.net import _UA


class CompanySearchIn(BaseModel):
    companies: list[str] = Field(min_length=1)
    query: str = ""
    limit: int = Field(default=15, ge=1, le=50)


def register_company_routes(app: FastAPI) -> None:
    @app.get("/companies")
    def companies(request: Request) -> dict:
        store = request.app.state.store
        counts: dict[str, int] = {}
        for job in store.list_jobs():
            counts[job.source] = counts.get(job.source, 0) + 1
        # openai and anthropic are stored under the ats name, so match on company too
        by_name: dict[str, int] = {}
        for job in store.list_jobs():
            by_name[job.company.lower()] = by_name.get(job.company.lower(), 0) + 1
        return {
            "companies": [
                {
                    "id": c.id, "name": c.name, "careers_url": c.careers_url, "ats": c.ats,
                    "sign_in": c.sign_in, "how": c.how,
                    "saved_jobs": by_name.get(c.name.lower(), 0),
                }
                for c in COMPANIES
            ],
            "note": "Read-only. ApplyPilot does not sign in to these sites or submit anything. "
                    "Open the posting and apply there yourself.",
        }

    @app.post("/companies/search")
    def company_search(body: CompanySearchIn, request: Request) -> dict:
        unknown = [c for c in body.companies if c not in BY_ID]
        if unknown:
            raise HTTPException(400, f"unknown company: {', '.join(unknown)}")
        settings = request.app.state.settings
        store = request.app.state.store
        client = httpx.Client(timeout=settings.http_timeout_s, headers={"user-agent": _UA},
                              follow_redirects=True)
        try:
            found, errors = search_companies(
                body.companies, body.query, limit=body.limit, client=client,
                timeout=settings.http_timeout_s, retries=min(settings.http_retries, 2),
            )
            saved, save_errors = persist_jobs(store, request.app.state.embedder, found)
        finally:
            client.close()
        errors = [*errors, *save_errors]
        for err in errors:
            store.add_run(step="discovery", ok=False, message=err)
        store.add_run(
            step="discovery", ok=not errors,
            message=f"{len(saved)} jobs from {', '.join(body.companies)}",
            detail={"companies": body.companies, "query": body.query, "saved": len(saved)},
        )
        return {
            "saved": len(saved), "created": sum(1 for _, created in saved if created),
            "errors": errors,
            "jobs": [
                {"job_id": j.job_id, "company": j.company, "title": j.title, "url": j.url,
                 "location": (j.metadata or {}).get("location", ""), "created": created}
                for j, created in saved
            ],
        }
