"""Alarm Triage read-only module.

Converts an alarm JSON into validation results, context pack, and a draft
ServiceNow payload (JSON + Markdown) plus a zipped artifact.

CLI usage:
    python -m scripts.alarm_triage.triage --alarm demo/alarms/A001.json --out outputs/A001 --offline
"""

__all__ = [
    "triage",
]
