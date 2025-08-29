from __future__ import annotations

import json
from pathlib import Path

from scripts.alarm_triage.triage import triage_batch


def test_demo_alarms_integration(tmp_path: Path):
    out = tmp_path / "batch"
    summary = triage_batch("demo/alarms/*.json", out, offline=True, emit_draft=True)
    assert summary["count"] >= 1
    # For each alarm ensure validation + draft.md exist
    for alarm_id in summary["alarms"]:
        single = out / alarm_id
        val = single / "validation.json"
        draft = single / "snow_draft.md"
        assert val.is_file(), f"missing validation.json for {alarm_id}"
        assert draft.is_file(), f"missing snow_draft.md for {alarm_id}"
        # sanity content
        data = json.loads(val.read_text(encoding="utf-8"))
        assert data.get("alarm_id") == alarm_id
