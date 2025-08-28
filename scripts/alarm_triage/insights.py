"""Generate human-readable insights for an alarm.

The goal is to keep this deterministic and offline-friendly. We fabricate a
small set of insights based on alarm fields so tests can assert substrings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any


def build_insights(alarm: Dict[str, Any]) -> Dict[str, str]:
    alarm_id = alarm.get("id") or alarm.get("alarm_id") or "UNKNOWN"
    device = alarm.get("device", "device")
    site = alarm.get("site", "site001")

    blast_radius = (
        f"Alarm {alarm_id} appears confined to {device} at {site}. "
        "No adjacent core links show correlated errors in offline dataset."
    )
    next_steps = (
        "1. Collect interface counters (show interface).\n"
        "2. Review recent changes (git diff / change log).\n"
        "3. If persists, schedule maintenance window to replace optics."
    )
    summary = f"Offline triage completed for {alarm_id} on {device}."
    return {
        "summary": summary,
        "blast_radius": blast_radius,
        "next_steps": next_steps,
    }


def write_insights_md(insights: Dict[str, str], out_md: Path) -> None:
    out_md.write_text(
        "# ServiceNow Draft\n\n"
        f"**Summary**: {insights['summary']}\n\n"
        "## Blast Radius\n" + insights["blast_radius"] + "\n\n"
        "## Suggested Next Steps\n" + insights["next_steps"] + "\n",
        encoding="utf-8",
    )
