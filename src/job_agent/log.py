"""One json line per event. Good enough to grep when a run goes sideways."""

from __future__ import annotations

import json
import logging
import sys

_CONFIGURED = False


class _JsonFmt(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "lvl": record.levelname.lower(),
            "msg": record.getMessage(),
            "logger": record.name,
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger() -> logging.Logger:
    global _CONFIGURED
    log = logging.getLogger("applypilot")
    if not _CONFIGURED:
        log.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFmt())
        log.addHandler(handler)
        log.propagate = False
        _CONFIGURED = True
    return log


def event(step: str, *, ok: bool = True, **fields) -> None:
    level = logging.INFO if ok else logging.WARNING
    get_logger().log(level, step, extra={"fields": {"step": step, "ok": ok, **fields}})
