"""Langfuse tracing hook — STUB (Phase 8).

``trace_step`` is applied to agent functions now so call sites don't change later.
Today it is a pass-through: it does NOT send anything to Langfuse.

TODO(phase-8):
  - If LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are set and ``langfuse`` is installed,
    wrap the call in a Langfuse span/observation (inputs, outputs, latency, errors).
  - Propagate a run/trace id from the orchestrator so every agent step nests under one trace.
  - Record LiteLLM token usage and cost per step (LiteLLM has a Langfuse callback).
  - Never log raw resume PII beyond what the user has consented to.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def trace_step(name: str) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # TODO(phase-8): open a Langfuse span named `name` here.
            return fn(*args, **kwargs)

        wrapper.__trace_name__ = name  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
