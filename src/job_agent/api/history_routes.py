"""History tab: applications imported from an export, joined to jobs, resumes and events."""

from __future__ import annotations

import json

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from job_agent.history import HistoryError, HistoryStore

MAX_IMPORT_BYTES = 30 * 1024 * 1024


def register_history_routes(app: FastAPI) -> None:
    app.state.history = HistoryStore(app.state.settings.history_path)

    @app.get("/history/summary")
    def history_summary(request: Request) -> dict:
        return request.app.state.history.summary()

    @app.get("/history/applications")
    def history_applications(
        request: Request, company: str | None = None, status: str | None = None,
        q: str | None = None, offset: int = 0, limit: int = 50,
    ) -> dict:
        return request.app.state.history.applications(
            company=company, status=status, q=q,
            offset=max(offset, 0), limit=max(1, min(limit, 200)),
        )

    @app.get("/history/applications/{application_id}")
    def history_detail(application_id: str, request: Request) -> dict:
        found = request.app.state.history.detail(application_id)
        if found is None:
            raise HTTPException(404, "application not found")
        return found

    @app.post("/history/import")
    async def history_import(request: Request, file: UploadFile = File(...)) -> dict:
        raw = await file.read(MAX_IMPORT_BYTES + 1)
        if len(raw) > MAX_IMPORT_BYTES:
            raise HTTPException(413, "export is larger than 30 MB")
        try:
            return request.app.state.history.import_doc(json.loads(raw))
        except (ValueError, KeyError, TypeError, HistoryError) as exc:
            raise HTTPException(422, f"not a valid export: {exc}") from exc
