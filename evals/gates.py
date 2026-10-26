"""Eval gates from the plan — config SKELETON (Phase 2-3).

Thresholds here are the single source of truth for CI. Only ``keyword_coverage`` is
implemented (a deterministic string check); the DeepEval-backed metrics are built in
``deepeval_suite.py`` and need an LLM judge (not run in Phase 1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Gate:
    name: str
    checks: str
    threshold: float | None
    kind: str = "min_score"  # "min_score" | "pass_fail"
    hard_fail: bool = False


GATES: list[Gate] = [
    Gate("faithfulness", "No skill/title/employer absent from the original resume", 1.0, hard_fail=True),
    Gate("answer_relevancy", "Tailored resume addresses the JD's required skills", 0.8),
    Gate("keyword_coverage", "Share of must-have JD keywords present", 0.7),
    Gate("retrieval_precision", "Top-5 retrieved chunks relevant to the JD", 0.8),
    Gate("format_check", "Renders, exactly one version, no broken sections", None, kind="pass_fail"),
]

DATASET_SIZE = 20  # fixed resume/JD pairs; each human correction is appended


def keyword_coverage(must_have: list[str], resume_text: str) -> float:
    """Fraction of must-have keywords found (case-insensitive, whole-token)."""
    if not must_have:
        return 1.0
    text = resume_text.lower()
    hits = sum(
        1 for kw in must_have
        if re.search(rf"(?<![a-z0-9]){re.escape(kw.lower())}(?![a-z0-9])", text)
    )
    return hits / len(must_have)
