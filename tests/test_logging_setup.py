import json
import logging
import threading
from typing import List
from io import StringIO

import pytest

from scripts.alarm_triage.logging_setup import (
    configure_json_logging,
    get_logger,
    RESERVED,
)


def _get_alarm_logger(name="alarm_triage"):
    return logging.getLogger(name)


def test_single_handler_and_level_update(capfd):
    logger = configure_json_logging(level="WARNING")
    # Ensure one handler
    handlers = [h for h in logger.handlers if getattr(h, "_alarm_json", False)]
    assert len(handlers) == 1
    assert logger.level == logging.WARNING

    # Update level
    logger2 = configure_json_logging(level="DEBUG")
    assert logger is logger2
    handlers2 = [h for h in logger2.handlers if getattr(h, "_alarm_json", False)]
    assert len(handlers2) == 1
    assert logger2.level == logging.DEBUG


def test_json_shape_and_timezone():
    buf = StringIO()
    logger = configure_json_logging(level="INFO", stream=buf, force=True)
    logger.info("hello", extra={"event": "say_hello", "fields": {"a": 1}})
    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)

    assert payload["msg"] == "hello"
    assert payload["level"] == "info"
    assert payload["event"] == "say_hello"
    assert payload["fields"] == {"a": 1}
    assert payload["ts"].endswith("Z")
    # Check millisecond precision (3 digits before Z after decimal)
    assert "." in payload["ts"]
    ms_part = payload["ts"].split(".")[-1].rstrip("Z")
    assert len(ms_part) == 3


def test_avoid_event_duplication():
    buf = StringIO()
    logger = configure_json_logging(level="INFO", stream=buf, force=True)
    logger.info("same", extra={"event": "same", "fields": {}})
    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert "event" not in payload  # event duplicated so removed


def test_non_serializable_field_is_stringified():
    class X: ...
    obj = X()
    buf = StringIO()
    logger = configure_json_logging(level="INFO", stream=buf, force=True)
    logger.info("obj", extra={"fields": {"obj": obj}})
    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert isinstance(payload["fields"]["obj"], str)


def test_reserved_keys_not_overwritten():
    buf = StringIO()
    logger = configure_json_logging(level="INFO", stream=buf, force=True)
    logger.info("reserve", extra={"fields": {k: f"bad_{k}" for k in list(RESERVED)[:3]}})
    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    # Original values intact
    assert payload["msg"] == "reserve"
    # The intruding reserved keys should appear under fields as provided
    for k in list(RESERVED)[:3]:
        assert k in payload["fields"]


def test_propagation_disabled():
    logger = configure_json_logging(level="INFO")
    assert logger.propagate is False


def test_threadsafe_config_race():
    results: List[logging.Logger] = []

    def worker():
        results.append(configure_json_logging(level="INFO"))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    logger = results[0]
    handlers = [h for h in logger.handlers if getattr(h, "_alarm_json", False)]
    assert len(handlers) == 1
