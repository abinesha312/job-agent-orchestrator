"""Mandatory approval gate: nothing auto-submits or auto-emails."""

from job_agent.approval.gate import (
    ApprovalRequiredError,
    InvalidTransitionError,
    approve,
    require_approval,
    requires_approval,
    send_outreach_email,
    submit_application,
    transition,
)

__all__ = [
    "ApprovalRequiredError",
    "InvalidTransitionError",
    "approve",
    "require_approval",
    "requires_approval",
    "send_outreach_email",
    "submit_application",
    "transition",
]
