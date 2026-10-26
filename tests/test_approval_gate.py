from __future__ import annotations

import pytest

from job_agent.approval import (
    ApprovalRequiredError,
    InvalidTransitionError,
    approve,
    require_approval,
    send_outreach_email,
    submit_application,
    transition,
)
from job_agent.db.models import ApplicationStatus as S


def app(status=S.awaiting_approval, approved=False):
    return {"status": status, "approved_by_user": approved, "metadata": {}}


@pytest.mark.parametrize("approved", [False, None, "true", 1, "yes"])
def test_submit_raises_without_explicit_approval(approved):
    with pytest.raises(ApprovalRequiredError):
        submit_application(app(S.approved, approved))


def test_submit_raises_when_flag_missing():
    with pytest.raises(ApprovalRequiredError):
        submit_application({"status": "approved"})


def test_send_email_raises_without_approval():
    with pytest.raises(ApprovalRequiredError):
        send_outreach_email(app(), to="recruiter@example.com", subject="Hi", body="...")


def test_flag_alone_is_not_enough_status_must_be_approved():
    with pytest.raises(ApprovalRequiredError):
        require_approval(app(S.tailored, True))


def test_approved_path_reaches_stub_but_sends_nothing():
    a = approve(app(), approved_by="user")
    assert a["approved_by_user"] is True and a["status"] == S.approved
    assert a["metadata"]["approved_by"] == "user"
    with pytest.raises(NotImplementedError):
        submit_application(a)
    with pytest.raises(NotImplementedError):
        send_outreach_email(a, to="r@example.com", subject="s", body="b")


def test_agents_cannot_self_approve_or_skip_ahead():
    with pytest.raises(ApprovalRequiredError):
        transition(app(), S.approved)
    with pytest.raises(InvalidTransitionError):
        transition(app(S.tailored), S.applied)
    with pytest.raises(InvalidTransitionError):
        approve(app(S.tailored), approved_by="user")
    with pytest.raises(ApprovalRequiredError):
        approve(app(), approved_by="  ")


def test_happy_path_transitions():
    a = app(S.discovered)
    for s in (S.matched, S.tailored, S.awaiting_approval):
        transition(a, s)
    approve(a, approved_by="user")
    transition(a, S.applied)
    assert a["status"] == S.applied


def test_status_values_match_plan():
    assert [s.value for s in S] == [
        "discovered", "matched", "tailored", "awaiting_approval", "approved", "applied", "rejected"
    ]
