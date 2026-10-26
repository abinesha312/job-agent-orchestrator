"""Email finder agent — STUB (Phase 5).

Finds recruiter / hiring-manager contacts for a job via the Apollo API and stores them
in ``contacts`` (source='apollo', verified from Apollo's email status). FINDING only —
this agent never sends email. Sending goes through
``job_agent.approval.gate.send_outreach_email``, which requires approved_by_user=True.

TODO(phase-5):
  - Apollo people search by company domain + titles (recruiter, talent acquisition,
    hiring manager for the role); then enrichment to reveal email (consumes Apollo credits —
    add a daily budget cap before enabling).
  - Mark verified only when Apollo reports a verified email status.
  - Exit criterion: verified emails for 80% of test jobs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass
class FoundContact:
    name: str
    title: str | None
    email: str | None
    verified: bool
    source: str = "apollo"


def find_contacts(job_id: uuid.UUID, *, max_contacts: int = 3) -> list[FoundContact]:
    raise NotImplementedError("Phase 5: Apollo email finder not implemented yet")
