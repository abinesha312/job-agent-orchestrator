"""A few leftovers from the foundation: the gate numbers, and the autogen stub."""

import uuid

import pytest

from job_agent.agents.orchestrator import Orchestrator, get_orchestrator

U = uuid.uuid4()


def test_autogen_stays_unimplemented():
    orch = get_orchestrator("autogen")
    with pytest.raises(NotImplementedError):
        orch.run(U, U)
    with pytest.raises(NotImplementedError):
        orch.resume_after_approval(U)


def test_orchestrators_share_interface():
    for kind in ("state_machine", "maf", "autogen"):
        assert isinstance(get_orchestrator(kind), Orchestrator)
    with pytest.raises(ValueError):
        get_orchestrator("bogus")


def test_eval_gate_thresholds_match_plan():
    from evals import gates

    g = {x.name: x for x in gates.GATES}
    assert g["faithfulness"].threshold == 1.0 and g["faithfulness"].hard_fail
    assert g["answer_relevancy"].threshold == 0.8
    assert g["keyword_coverage"].threshold == 0.7
    assert g["retrieval_precision"].threshold == 0.8
    assert g["format_check"].kind == "pass_fail"
    assert gates.keyword_coverage(["python", "docker", "go"], "Python and Docker") == pytest.approx(2 / 3)
