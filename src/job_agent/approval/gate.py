"""Approval gate (REAL logic, Phase 1) + submit/send entry points (STUBS).

Rules enforced here — and backstopped in Postgres by the
``ck_applications_approval_required`` CHECK constraint:

1. Every path that submits an application or sends an email goes through
   ``require_approval`` and raises ``ApprovalRequiredError`` unless
   ``approved_by_user is True`` (strict identity; truthy values like "yes" or 1 fail).
2. Status may only move to ``approved`` via ``approve(..., approved_by=...)``, which
   is the single place ``approved_by_user`` becomes True (meant to be called from a
   user action in the UI/API, never from an agent).
3. ``applied`` is reachable only from ``approved``.

There is deliberately no auto-submit / auto-email mode. The plan's open question
("auto-submit where allowed?") is resolved as: approve every application.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, TypeVar

from job_agent.db.models import ApplicationStatus as S

F = TypeVar("F", bound=Callable[..., Any])


class ApprovalRequiredError(PermissionError):
    """Raised when a submit/send path is attempted without explicit user approval."""


class InvalidTransitionError(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[S, set[S]] = {
    S.discovered: {S.matched, S.rejected},
    S.matched: {S.tailored, S.rejected},
    S.tailored: {S.awaiting_approval, S.rejected},
    S.awaiting_approval: {S.approved, S.rejected, S.tailored},  # tailored = user asked for edits
    S.approved: {S.applied, S.rejected},
    S.applied: {S.rejected},  # employer rejection after applying
    S.rejected: set(),
}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _set(obj: Any, key: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[key] = value
    else:
        setattr(obj, key, value)


def require_approval(application: Any) -> None:
    """Raise unless the application (dict or object) has ``approved_by_user is True``."""
    if _get(application, "approved_by_user", None) is not True:
        raise ApprovalRequiredError(
            "approved_by_user must be True before any submit or send; "
            "the user must approve this application explicitly."
        )
    status = _get(application, "status", None)
    if status is not None and S(status) not in (S.approved, S.applied):
        raise ApprovalRequiredError(f"status is {S(status).value!r}; must be 'approved' to submit/send")


def requires_approval(fn: F) -> F:
    """Decorator for any function whose first argument is the application record."""

    @functools.wraps(fn)
    def wrapper(application: Any, *args: Any, **kwargs: Any) -> Any:
        require_approval(application)
        return fn(application, *args, **kwargs)

    wrapper.__requires_approval__ = True  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


def transition(application: Any, new_status: S | str) -> Any:
    """Move an application to ``new_status`` if allowed. ``approved`` is blocked here."""
    current = S(_get(application, "status", S.discovered))
    target = S(new_status)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransitionError(f"{current.value} -> {target.value} not allowed")
    if target == S.approved:
        raise ApprovalRequiredError("Use approve(application, approved_by=...) — agents cannot self-approve")
    if target == S.applied:
        require_approval(application)
    _set(application, "status", target)
    return application


def approve(application: Any, *, approved_by: str) -> Any:
    """Record explicit user approval. The ONLY function that sets approved_by_user=True."""
    if not approved_by or not approved_by.strip():
        raise ApprovalRequiredError("approved_by (the approving user) is required")
    current = S(_get(application, "status", S.discovered))
    if current != S.awaiting_approval:
        raise InvalidTransitionError(f"Can only approve from awaiting_approval, not {current.value}")
    _set(application, "approved_by_user", True)
    _set(application, "status", S.approved)
    meta = _get(application, "metadata", None)
    if isinstance(meta, dict):
        meta["approved_by"] = approved_by
        meta["approved_at"] = datetime.now(UTC).isoformat()
    return application


@requires_approval
def submit_application(application: Any, **kwargs: Any) -> None:
    # kept on purpose. the user marks applied after they submit it themselves.
    raise NotImplementedError("submission stays manual; nothing was submitted.")


@requires_approval
def send_outreach_email(application: Any, *, to: str, subject: str, body: str) -> None:
    # we never send. the draft sits there until the user copies it.
    raise NotImplementedError("email sending is not implemented; nothing was sent.")
