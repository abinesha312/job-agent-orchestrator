"""Stubs must fail loudly rather than pretend to work."""

import uuid

import pytest

from job_agent.agents import email_finder, job_discovery, retrieval, tailoring
from job_agent.agents.orchestrator import Orchestrator, get_orchestrator

U = uuid.uuid4()


@pytest.mark.parametrize("call", [
    lambda: retrieval.retrieve_chunks_for_job(U, U),
    lambda: tailoring.tailor_resume(U, U),
    lambda: job_discovery.fetch_greenhouse("x"),
    lambda: job_discovery.fetch_lever("x"),
    lambda: job_discovery.fetch_adzuna("python"),
    lambda: email_finder.find_contacts(U),
    lambda: get_orchestrator("state_machine").run(U, U),
    lambda: get_orchestrator("maf").run(U, U),
    lambda: get_orchestrator("autogen").run(U, U),
])
def test_stubs_raise_not_implemented(call):
    with pytest.raises(NotImplementedError):
        call()


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
