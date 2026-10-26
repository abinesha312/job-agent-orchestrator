"""Langfuse span if the keys are set. Otherwise this is a no-op."""

from __future__ import annotations

import functools
import os
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

_client = None
_client_key = ""


def _langfuse():
    global _client, _client_key
    pub = os.environ.get("LANGFUSE_PUBLIC_KEY") or ""
    sec = os.environ.get("LANGFUSE_SECRET_KEY") or ""
    if not pub or not sec:
        return None
    key = pub + "|" + sec
    if _client is not None and _client_key == key:
        return _client
    try:
        from langfuse import Langfuse
    except ImportError:
        return None
    try:
        _client = Langfuse(
            public_key=pub, secret_key=sec, host=os.environ.get("LANGFUSE_HOST") or None,
        )
        _client_key = key
        return _client
    except Exception:
        return None


def trace_step(name: str) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            client = _langfuse()
            if client is None:
                return fn(*args, **kwargs)
            span = None
            try:
                trace = client.trace(name=name)
                span = trace.span(name=name)
            except Exception:
                return fn(*args, **kwargs)
            try:
                out = fn(*args, **kwargs)
            except Exception as exc:
                try:
                    span.end(level="ERROR", status_message=str(exc)[:400])
                except Exception:
                    pass
                raise
            try:
                # don't ship resume text off the box; just note that the step finished
                span.end(output={"ok": True})
            except Exception:
                pass
            return out

        wrapper.__trace_name__ = name  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
