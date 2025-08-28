"""Probe helpers (ping / traceroute) with offline fallback.

In offline mode we load pre-baked probe results from demo/alarms/probes_offline.json.
In online mode we attempt lightweight ping/traceroute with timeouts, but only
if explicitly requested (not used in CI). This keeps the solution read-only.
"""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, List

DEFAULT_TIMEOUT = 3  # seconds per probe


def _run_command(cmd: List[str], timeout: int = DEFAULT_TIMEOUT) -> str:
    try:
        out = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
            text=True,
        )
        return out.stdout[:5000]
    except Exception as exc:  # pragma: no cover - defensive
        return f"error: {exc}"


def _online_probes(target: str) -> Dict[str, Any]:  # pragma: no cover - not in CI
    system = platform.system().lower()
    if system == "windows":
        ping_cmd = ["ping", "-n", "2", target]
        trace_cmd = ["tracert", "-d", target]
    else:
        ping_cmd = ["ping", "-c", "2", "-W", "1", target]
        trace_cmd = ["traceroute", "-n", "-m", "5", target]
    return {
        "ping": _run_command(ping_cmd),
        "traceroute": _run_command(trace_cmd),
    }


def load_offline_probes(probes_file: Path) -> Dict[str, Any]:
    if probes_file.is_file():
        try:
            return json.loads(probes_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"error": "invalid probes_offline.json"}
    return {"error": "missing probes_offline.json"}


def gather_probes(target: str, repo_root: Path, offline: bool) -> Dict[str, Any]:
    if offline:
        return load_offline_probes(repo_root / "demo" / "alarms" / "probes_offline.json")
    return _online_probes(target)
