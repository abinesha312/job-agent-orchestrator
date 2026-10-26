"""Optional DeepEval pass. The offline gates already run via `python -m evals`.

If deepeval is installed this file re-checks the same synthetic pairs with the
deterministic metrics. The LLM judge only runs when LLM_JUDGE=on and a key is set.
"""

from __future__ import annotations

import os

import pytest

deepeval = pytest.importorskip("deepeval")

from job_agent.checks import DATASET_SIZE  # noqa: E402
from job_agent.evalrun import run_dataset  # noqa: E402


def test_offline_gates_on_golden_pairs():
    rows = run_dataset()
    assert len(rows) == DATASET_SIZE
    failed = [row["id"] for row in rows if not row["passed"]]
    assert not failed, failed


@pytest.mark.skipif(
    os.environ.get("LLM_JUDGE", "auto") == "off" or not (
        os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    ),
    reason="LLM judge needs a key and LLM_JUDGE!=off",
)
def test_llm_judge_importable():
    # touched so the skip is explicit. the real call happens inside evaluate()
    # when a pipeline runs with a key. we don't spend tokens from this file.
    assert deepeval is not None
