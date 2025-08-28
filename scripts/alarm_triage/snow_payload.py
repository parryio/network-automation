"""Render a deterministic ServiceNow style draft payload and markdown."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any


def build_snow_payload(alarm: Dict[str, Any], insights: Dict[str, str]) -> Dict[str, Any]:
    return {
        "short_description": f"Alarm {alarm.get('id')} triage summary",
        "alarm_id": alarm.get("id"),
        "device": alarm.get("device"),
        "site": alarm.get("site"),
        "severity": alarm.get("severity"),
        "insights": insights,
    }


def write_payload(payload: Dict[str, Any], out_json: Path) -> None:
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
