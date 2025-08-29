from __future__ import annotations

from pathlib import Path


APP_DIRS = {"ui", "utils", "scripts"}


def _grep(root: Path, needle: str) -> list[Path]:
    hits = []
    for p in root.rglob("*.py"):
        sp = str(p)
        # limit to application directories
        if not any(f"/{d}/" in sp for d in APP_DIRS):
            continue
        if any(skip in sp for skip in (".venv", "__pycache__")):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if needle in text:
            hits.append(p)
    return hits


def test_no_experimental_rerun():
    assert not _grep(Path("."), "experimental_rerun"), "Remove st.experimental_rerun; use compat.rerun()."


def test_no_use_container_width():
    assert not _grep(Path("."), "use_container_width"), "Replace use_container_width with width='stretch'."
