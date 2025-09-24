"""Configuration normalization utilities."""

from __future__ import annotations

from typing import Iterable, List


IGNORED_PREFIXES = ("!", "#")


def normalize_config(config_text: str) -> List[str]:
    """Normalize a raw configuration into comparable logical lines."""

    normalized: List[str] = []
    for raw_line in config_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith(IGNORED_PREFIXES):
            continue
        collapsed = " ".join(stripped.split())
        normalized.append(collapsed)
    return normalized


def join_lines(lines: Iterable[str]) -> str:
    """Join normalized lines for string based matching."""

    return "\n".join(lines)
