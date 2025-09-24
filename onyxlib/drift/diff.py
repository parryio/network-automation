"""Diff helpers for configuration drift."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import difflib


@dataclass
class DiffResult:
    device: str
    diff_text: str
    line_count: int
    diff_path: Path


def build_diff(device: str, baseline_lines: Iterable[str], running_lines: Iterable[str], out_dir: Path) -> DiffResult:
    """Create a unified diff for a device and persist it to disk."""

    out_dir.mkdir(parents=True, exist_ok=True)
    diff_path = out_dir / f"{device}.diff"

    baseline_list = list(baseline_lines)
    running_list = list(running_lines)

    diff_lines = list(
        difflib.unified_diff(
            baseline_list,
            running_list,
            fromfile=f"{device} (baseline)",
            tofile=f"{device} (running)",
            lineterm="",
        )
    )

    diff_text = "\n".join(diff_lines)
    diff_path.write_text(diff_text)

    line_count = sum(1 for line in diff_lines if line.startswith(('+', '-')) and not line.startswith(('+++', '---')))

    return DiffResult(device=device, diff_text=diff_text, line_count=line_count, diff_path=diff_path)
