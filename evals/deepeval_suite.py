"""DeepEval suite — SKELETON (Phase 2-3). Not collected by the default pytest run.

Run later with:  pip install -e '.[evals]'  &&  deepeval test run evals/deepeval_suite.py

TODO(phase-2/3):
  - Load evals/datasets/pairs.jsonl (20 synthetic resume/JD pairs; see datasets/README.md).
  - For each pair: run retrieval + tailoring, build an LLMTestCase
    (input=JD, actual_output=tailored resume, retrieval_context=top-5 chunks,
    context=original resume chunks).
  - Metrics: FaithfulnessMetric(threshold=1.0), AnswerRelevancyMetric(threshold=0.8),
    ContextualPrecisionMetric(threshold=0.8) for retrieval precision, a custom
    keyword-coverage metric (gates.keyword_coverage, >= 0.7), and a format check.
  - Configure the judge model to Gemini via LiteLLM; never call paid APIs in unit tests.
  - Any failure => version goes to human review, never to the approval queue.
"""

from __future__ import annotations

import pytest

from evals.gates import GATES  # noqa: F401  (thresholds source of truth)

deepeval = pytest.importorskip("deepeval")


@pytest.mark.skip(reason="Phase 2-3: tailoring agent and dataset not built yet")
def test_eval_gates_on_fixed_pairs():
    raise NotImplementedError
