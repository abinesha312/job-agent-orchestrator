"""Orchestrator interface (Phase 6 for the full pipeline).

The orchestrator routes a job through the agents, tracks application status and
pauses at ``awaiting_approval``. It sits behind the ``Orchestrator`` ABC so the
backing framework is swappable:

  - ``StateMachineOrchestrator``: plain-Python default (no framework dependency).
  - ``MicrosoftAgentFrameworkOrchestrator``: adapter stub for Microsoft Agent Framework,
    AutoGen's successor (MAF 1.0 GA'd April 2026).
  - ``AutoGenOrchestrator``: adapter stub kept for parity with the plan. As of Oct 2026
    the AutoGen repo is archived / no longer maintained by Microsoft, so prefer MAF.

Invariants every implementation must keep:
  - Agents are plain functions in ``job_agent.agents`` — the framework only routes.
  - A run never goes past ``awaiting_approval``; approval comes from the user via
    ``approval.gate.approve``. Submission/sending go through the approval gate.
  - Step limit per run and daily budget cap (plan risk: agent loops / LLM cost).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from job_agent.db.models import ApplicationStatus


@dataclass
class RunResult:
    job_id: uuid.UUID
    status: ApplicationStatus
    steps: list[str] = field(default_factory=list)
    needs_human_review: bool = False
    notes: list[str] = field(default_factory=list)


class Orchestrator(ABC):
    max_steps: int = 20

    @abstractmethod
    def run(self, job_id: uuid.UUID, resume_id: uuid.UUID) -> RunResult:
        """Drive one job from discovered/matched up to awaiting_approval (never further)."""

    @abstractmethod
    def resume_after_approval(self, application_id: uuid.UUID) -> RunResult:
        """Continue after the user approved: prepare the packet for user submission."""


class StateMachineOrchestrator(Orchestrator):
    """Plain-Python state machine. STUB.

    TODO(phase-6): matched (retrieval.score_match) -> tailored (tailoring.tailor_resume +
    eval gates) -> awaiting_approval; email_finder.find_contacts in parallel. Persist
    status transitions via approval.gate.transition. Stop on step limit.
    """

    def run(self, job_id: uuid.UUID, resume_id: uuid.UUID) -> RunResult:
        raise NotImplementedError("Phase 6: orchestrator pipeline not implemented yet")

    def resume_after_approval(self, application_id: uuid.UUID) -> RunResult:
        raise NotImplementedError("Phase 6: post-approval flow not implemented yet")


class MicrosoftAgentFrameworkOrchestrator(Orchestrator):
    """Adapter for Microsoft Agent Framework (``agent-framework`` on PyPI). STUB.

    TODO(phase-6): wrap each agent function as a MAF tool/executor and build a workflow
    graph with a human-in-the-loop request at awaiting_approval.
    """

    def run(self, job_id: uuid.UUID, resume_id: uuid.UUID) -> RunResult:
        raise NotImplementedError("Phase 6: MAF adapter not implemented")

    def resume_after_approval(self, application_id: uuid.UUID) -> RunResult:
        raise NotImplementedError("Phase 6: MAF adapter not implemented")


class AutoGenOrchestrator(Orchestrator):
    """Adapter for AutoGen group chat. STUB — AutoGen is archived; prefer MAF."""

    def run(self, job_id: uuid.UUID, resume_id: uuid.UUID) -> RunResult:
        raise NotImplementedError("AutoGen adapter not implemented (AutoGen is archived)")

    def resume_after_approval(self, application_id: uuid.UUID) -> RunResult:
        raise NotImplementedError("AutoGen adapter not implemented (AutoGen is archived)")


_REGISTRY: dict[str, type[Orchestrator]] = {
    "state_machine": StateMachineOrchestrator,
    "maf": MicrosoftAgentFrameworkOrchestrator,
    "autogen": AutoGenOrchestrator,
}


def get_orchestrator(kind: str = "state_machine") -> Orchestrator:
    try:
        return _REGISTRY[kind]()
    except KeyError as exc:
        raise ValueError(f"Unknown orchestrator {kind!r}; choose from {sorted(_REGISTRY)}") from exc
