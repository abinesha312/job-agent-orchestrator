"""Tailoring agent — STUB (Phase 2-3).

Purpose: rewrite the resume for one job using ONLY facts present in the original
resume, and save the result as a new ``resume_versions`` row (parent_id = source version,
job_id = target job).

TODO(phase-2/3):
  - Prompt Gemini via LiteLLM with retrieved chunks + JD; reorder/rephrase, never invent.
  - Render to DOCX/PDF from a resume template; store file_path.
  - Run DeepEval gates (evals/): faithfulness must be 1.0 (hard fail) — any skill, title
    or employer not in the original resume blocks the version. Failing versions go to
    human review and are never queued for approval.
  - On pass: application status tailored -> awaiting_approval (see approval.gate).
"""

from __future__ import annotations

import uuid


def tailor_resume(resume_version_id: uuid.UUID, job_id: uuid.UUID) -> uuid.UUID:
    """Create a tailored resume version and return its version_id. TODO(phase-2)."""
    raise NotImplementedError("Phase 2-3: tailoring agent not implemented yet")
