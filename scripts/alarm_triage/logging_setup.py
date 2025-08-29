from __future__ import annotations

"""Robust structured JSON logging for alarm triage CLI + UI.

Features:
 * Thread-safe idempotent configuration (no duplicate handlers)
 * Safe reconfiguration (log level & static fields update)
 * UTC timestamps with millisecond precision (Z suffix)
 * Lowercase level names, standard context fields
 * Resilient JSON serialization (non-serializable -> str)
 * Reserved key protection (user fields isolated under 'fields')

Usage example:
    from scripts.alarm_triage.logging_setup import configure_json_logging
    logger = configure_json_logging(level="INFO")
    logger.info(
        "High interface errors",
        extra={
            "event": "alarm_validated",
            "fields": {"alarm": "A001", "if": "xe-0/0/0"},
        },
    )

Convenience:
    from scripts.alarm_triage.logging_setup import get_logger
    log = get_logger(level="DEBUG")
    log.debug("debug message")
"""

from datetime import datetime, timezone
import json
import logging
import sys
from threading import RLock
from typing import Any, Mapping, MutableMapping

_DEFAULT_LOGGER_NAME = "alarm_triage"  # corrected typo

# Track configured handlers by logger name so we can update safely.
_configured_by_name: dict[str, logging.Handler] = {}
_lock = RLock()

RESERVED = {
    "ts",
    "level",
    "logger",
    "pid",
    "tid",
    "module",
    "func",
    "line",
    "msg",
    "event",
}


def _coerce_level(level: int | str) -> int:
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        lvl = logging._nameToLevel.get(level.upper())  # type: ignore[attr-defined]
        if isinstance(lvl, int):
            return lvl
    return logging.INFO


class JsonFormatter(logging.Formatter):
    """JSON log formatter safe against serialization errors."""

    def __init__(self, *, static: dict[str, Any] | None = None) -> None:  # noqa: D401
        super().__init__()
        self._static = static or {}

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        ts = (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        msg = record.getMessage()
        event = getattr(record, "event", None)
        if event == msg:
            event = None  # avoid duplication

        base: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname.lower(),
            "logger": record.name,
            "pid": record.process,
            "tid": record.thread,
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
            "msg": msg,
        }
        if event:
            base["event"] = event
        if self._static:
            base["static"] = self._static

        # Gather user fields (always nested under 'fields')
        fields_obj = getattr(record, "fields", {})
        user_fields: MutableMapping[str, Any]
        if isinstance(fields_obj, Mapping):
            user_fields = dict(fields_obj)  # shallow copy
        else:
            user_fields = {"_fields_type": str(type(fields_obj))}

        # Ensure reserved collisions do not overwrite base
        # (keep them inside fields as provided; base already set)
        if user_fields:
            base["fields"] = user_fields

        try:
            return json.dumps(
                base,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
        except Exception as exc:  # pragma: no cover (very unlikely)
            fallback = {
                "ts": ts,
                "level": "error",
                "logger": record.name,
                "msg": "log_serialization_failed",
                "error": str(exc),
            }
            return json.dumps(fallback, separators=(",", ":"))


def configure_json_logging(
    *,
    logger_name: str = _DEFAULT_LOGGER_NAME,
    level: int | str = "INFO",
    stream: Any | None = None,
    force: bool = False,
    extra_static: dict[str, Any] | None = None,
) -> logging.Logger:
    """Configure or update a structured JSON logger.

    Parameters
    ----------
    logger_name: Name of the logger to configure.
    level: Log level (int or name string).
    stream: Optional stream for the handler (defaults to sys.stdout).
    force: If True, remove any existing handler and re-add a fresh one.
    extra_static: Optional static metadata included under key 'static'.

    Returns
    -------
    logging.Logger: The configured logger instance.
    """
    numeric_level = _coerce_level(level)
    with _lock:
        logger = logging.getLogger(logger_name)
        logger.propagate = False
        logger.setLevel(numeric_level)

        existing_handler = None
        for h in logger.handlers:
            if getattr(h, "_alarm_json", False):  # type: ignore[attr-defined]
                existing_handler = h
                break

        if existing_handler and not force:
            # Update existing handler level/formatter & return
            existing_handler.setLevel(numeric_level)
            existing_handler.setFormatter(
                JsonFormatter(static=extra_static)
            )  # refresh static
            return logger

        # Remove old JSON handler if force
        if existing_handler and force:
            try:
                logger.removeHandler(existing_handler)
            except Exception:  # pragma: no cover
                pass

        # Avoid multiple handlers across repeated calls.
        handler = logging.StreamHandler(stream or sys.stdout)
        handler.setLevel(numeric_level)
        handler.setFormatter(JsonFormatter(static=extra_static))
        setattr(handler, "_alarm_json", True)  # mark for identification
        logger.addHandler(handler)
        _configured_by_name[logger_name] = handler
        return logger


def get_logger(name: str = _DEFAULT_LOGGER_NAME, **kwargs: Any) -> logging.Logger:
    """Convenience wrapper returning a configured logger.

    Accepts same keyword args as configure_json_logging (except logger_name / name).
    """
    if "logger_name" in kwargs:
        # guard to prevent mismatch
        raise TypeError("Use 'name' instead of 'logger_name' with get_logger().")
    return configure_json_logging(logger_name=name, **kwargs)


def log_event(event: str, **fields: Any) -> None:
    """Backwards-compatible helper to emit an info event.

    Provided for legacy call sites expecting the previous API.
    """
    logger = configure_json_logging()  # ensures default logger exists
    logger.info(event, extra={"event": event, "fields": fields})


__all__ = [
    "configure_json_logging",
    "get_logger",
    "log_event",
    "JsonFormatter",
    "RESERVED",
]
