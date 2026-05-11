"""Structured logging for A2A traffic.

Every task-scoped log line carries `session_id` and `task_id` so the audit
trail required by AC7 can be reconstructed from stdout alone.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


class _TaskAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = self.extra or {}
        prefix = f"[session={extra.get('session_id')} task={extra.get('task_id')}]"
        return f"{prefix} {msg}", kwargs


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level.upper())
    # Replace existing handlers so uvicorn's defaults don't double-log us.
    root.handlers = [handler]
    _CONFIGURED = True


def task_logger(*, session_id: str, task_id: str) -> _TaskAdapter:
    return _TaskAdapter(
        logging.getLogger("a2a"),
        {"session_id": session_id, "task_id": task_id},
    )
