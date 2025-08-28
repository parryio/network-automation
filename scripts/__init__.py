"""Top-level package marker so tests can `import scripts`.

Alarm triage tests import modules as `from scripts.alarm_triage import triage`.
Keeping this file minimal preserves existing behavior while ensuring
explicit package recognition under pytest collection.
"""

__all__ = [
	"alarm_triage",
]
