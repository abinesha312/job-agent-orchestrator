"""Static description of the main agent and its subagents, plus a roll-up of the run log.

The run log is the source of truth for what each agent did. Events carry the agent id in
``step`` (older events use ``discover`` and ``contacts``, mapped below).
"""

from __future__ import annotations

from dataclasses import dataclass

MAIN_ID = "orchestrator"


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    role: str
    tools: tuple[str, ...]
    order: int


SUBAGENTS: tuple[AgentSpec, ...] = (
    AgentSpec("resume", "Resume Agent", "Parses a PDF or DOCX, splits it into sections, stores chunks and embeddings.",
              ("extract_text", "chunk_resume", "embed"), 1),
    AgentSpec("discovery", "Job Discovery Agent", "Pulls roles from Greenhouse, Lever and Ashby, or a pasted job or URL.",
              ("discover_jobs", "import_manual", "import_from_url"), 2),
    AgentSpec("retrieval", "Retrieval Agent", "Embeds the job description and pulls the closest resume chunks, then scores the match.",
              ("score_match", "rank_scored"), 3),
    AgentSpec("email_finder", "Contact Finder Agent", "Looks for a public recruiter contact, otherwise guesses a pattern and marks it unverified.",
              ("find_contacts",), 4),
    AgentSpec("tailoring", "Tailoring Agent", "Rewrites the resume for the job and drafts a short email. Reorders only, without an LLM key.",
              ("tailor_resume", "fallback_resume", "fallback_email"), 5),
    AgentSpec("evaluator", "Quality Gate Agent", "Runs the faithfulness, relevancy, coverage, retrieval and format gates on every draft.",
              ("evaluate",), 6),
    AgentSpec("approval", "Approval Gate", "Human in the loop. Nothing is approved, applied or sent without the user.",
              ("approve", "transition"), 7),
)

_ALIASES = {"discover": "discovery", "contacts": "email_finder", "match": "retrieval",
            "tailor": "tailoring", "eval": "evaluator"}


def agent_of(step: str) -> str:
    return _ALIASES.get(step, step)


def _task(r) -> dict:
    return {
        "id": r.id, "agent": agent_of(r.step), "ok": r.ok, "message": r.message,
        "job_id": r.job_id, "resume_id": r.resume_id, "detail": r.detail, "created_at": r.created_at,
    }


def overview(store, limit: int = 500) -> dict:
    runs = store.list_runs(limit=limit)
    by_agent: dict[str, list] = {}
    for r in runs:
        by_agent.setdefault(agent_of(r.step), []).append(r)

    def card(spec_id: str, name: str, role: str, tools, order: int) -> dict:
        rows = by_agent.get(spec_id, [])
        last = rows[0] if rows else None
        failed = sum(1 for r in rows if not r.ok)
        if last is None:
            state = "idle"
        elif not last.ok:
            state = "error"
        else:
            state = "done"
        return {
            "id": spec_id, "name": name, "role": role, "tools": list(tools), "order": order,
            "state": state, "tasks_total": len(rows), "tasks_failed": failed,
            "last_run_at": last.created_at if last else None,
            "last_message": last.message if last else "",
            "recent_tasks": [_task(r) for r in rows[:8]],
        }

    subs = [card(s.id, s.name, s.role, s.tools, s.order) for s in SUBAGENTS]
    main = card(MAIN_ID, "Main Agent (Orchestrator)",
                "Walks each job from discovered to matched to tailored to awaiting approval. Never goes past approval.",
                ("run", "run_many", "resume_after_approval"), 0)
    main["subagents"] = [s["id"] for s in subs]
    return {"main": main, "subagents": subs, "total_tasks": len(runs)}


def timeline(store, job_id=None, limit: int = 200) -> list[dict]:
    rows = [r for r in store.list_runs(limit=limit) if job_id is None or r.job_id == job_id]
    return [_task(r) for r in reversed(rows)]
