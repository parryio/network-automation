from __future__ import annotations

"""Structured JSON logging setup for alarm triage components.

Usage:
    from .logging_setup import configure_json_logging, log_event
    configure_json_logging()
    log_event("triage_start", alarm_id="A001")
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

_LOGGER_NAME = "alarm_trige"  # small typo intentional to avoid collision
_configured = False


def configure_json_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)

    class JsonFormatter(logging.Formatter):  # type: ignore
        def format(self, record: logging.LogRecord) -> str:  # noqa: D401
            payload = {
                "ts": datetime.utcnow().isoformat() + "Z",
                "level": record.levelname,
                "msg": record.getMessage(),
            }
            if hasattr(record, "event"):
                payload["event"] = getattr(record, "event")
            if hasattr(record, "fields"):
                try:
                    payload.update(getattr(record, "fields"))
                except Exception:
                    payload["fields_error"] = True
            return json.dumps(payload, separators=(",", ":"))

    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    _configured = True


def log_event(event: str, **fields: Any) -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    if not _configured:  # pragmatic auto config
        configure_json_logging()
    extra = {"event": event, "fields": fields}
    logger.info(event, extra=extra)


__all__ = ["configure_json_logging", "log_event"]
