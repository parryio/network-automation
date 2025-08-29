from __future__ import annotations

from pathlib import Path


def test_ui_does_not_write_draft_directly():
    ui_file = Path("ui/app.py").read_text(encoding="utf-8")
    # Ensure no manual open/write of draft.md (only presence of string acceptable as read)
    assert "draft.md" not in [line.strip() for line in ui_file.splitlines() if ("write_text" in line or "open(" in line)], "UI should not author draft.md"
