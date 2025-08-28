"""Top-level package marker so tests can `import scripts`.

Consolidated after rebase: provides explicit package recognition under
pytest, exports alarm_triage, and avoids merge conflict markers.
"""

__all__ = ["alarm_triage"]
