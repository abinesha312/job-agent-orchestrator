"""Agent overview, task timeline and the Evals tab endpoints."""

from __future__ import annotations

import uuid
from collections import deque

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from job_agent import evals_service
from job_agent.agents import registry


class EvalRunIn(BaseModel):
    suite: str
    sample: int = 5


def register_agent_routes(app: FastAPI) -> None:
    app.state.eval_runs = deque(maxlen=60)

    @app.get("/agents")
    def agents(request: Request) -> dict:
        return registry.overview(request.app.state.store)

    @app.get("/agents/timeline")
    def agent_timeline(request: Request, job_id: uuid.UUID | None = None, limit: int = 200) -> dict:
        rows = registry.timeline(request.app.state.store, job_id, min(limit, 500))
        return {"count": len(rows), "events": rows}

    @app.get("/evals/catalog")
    def eval_catalog() -> dict:
        return evals_service.catalog()

    @app.post("/evals/run")
    def eval_run(body: EvalRunIn, request: Request) -> dict:
        try:
            result = evals_service.run_suite(
                body.suite, store=request.app.state.store, resumes=request.app.state.repository,
                sample=max(1, min(body.sample, 20)),
            )
        except KeyError as exc:
            raise HTTPException(404, f"unknown suite {body.suite}") from exc
        request.app.state.eval_runs.appendleft(result)
        request.app.state.store.add_run(
            step="evaluator", ok=result["status"] != "failed",
            message=f"eval suite {body.suite}: {result['status']} ({result['passed']}/{result['total']})",
            detail={"suite": body.suite, "summary": result["summary"]},
        )
        return result

    @app.get("/evals/runs")
    def eval_runs(request: Request) -> dict:
        rows = list(request.app.state.eval_runs)
        slim = [{k: v for k, v in r.items() if k != "cases"} for r in rows]
        return {"count": len(slim), "runs": slim}

    @app.get("/evals/runs/{run_id}")
    def eval_run_get(run_id: str, request: Request) -> dict:
        for r in request.app.state.eval_runs:
            if r["id"] == run_id:
                return r
        raise HTTPException(404, "run not found")
