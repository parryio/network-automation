from __future__ import annotations

"""ServiceNow draft generator.

make_draft(alarm, validation) -> markdown string used by UI.
"""

from typing import Dict, Any


def make_draft(alarm: Dict[str, Any], validation: Dict[str, Any]) -> str:
    aid = alarm.get("id", "UNKNOWN")
    device = alarm.get("device", "device")
    site = alarm.get("site", "site")
    status = validation.get("status", "n/a")
    lines = [
        "# ServiceNow Draft", "",
        f"**Alarm**: {aid}",
        f"**Device**: {device}",
        f"**Site**: {site}",
        f"**Validation Status**: {status}",
        "",
        "This draft was generated offline using deterministic demo data.",
    ]
    return "\n".join(lines) + "\n"

__all__ = ["make_draft"]
