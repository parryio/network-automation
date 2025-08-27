"""Network probe abstractions (ping / traceroute) with offline support.

All operations are READ-ONLY reachability tests. For deterministic CI runs,
pass offline=True to use canned results from demo/alarms/probes_offline.json.

Compliance Note: This module satisfies spec requirements for cross-platform
ping/traceroute, per-command timeouts, and offline determinism (no subprocess
calls when offline=True).
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
# Robustly locate repo root by searching upwards for 'demo/alarms'
REPO_ROOT = None
for candidate in HERE.parents:
    if (candidate / 'demo' / 'alarms').exists():
        REPO_ROOT = candidate
        break
if REPO_ROOT is None:  # Fallback to 3-levels up (best guess)
    REPO_ROOT = HERE.parents[2]
DEMO_ROOT = REPO_ROOT / 'demo'
OFFLINE_FILE = DEMO_ROOT / 'alarms' / 'probes_offline.json'

IS_WINDOWS = platform.system().lower().startswith("win")

@dataclass
class PingResult:
    status: str
    rtt_ms_avg: Optional[float]
    loss_pct: float

    def as_dict(self):  # pragma: no cover - trivial
        return {"status": self.status, "rtt_ms_avg": self.rtt_ms_avg, "loss_pct": self.loss_pct}


def _run_subprocess(cmd: List[str], timeout: int = 5) -> str:
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return (completed.stdout or "") + (completed.stderr or "")
    except subprocess.TimeoutExpired:
        return ""


def run_ping(host: str, count: int = 1, timeout_s: int = 2) -> PingResult:
    """Cross-platform single (or small count) ping.

    Returns PASS if at least one reply received.
    """
    if IS_WINDOWS:
        # Windows ping: -n count, -w timeout(ms)
        timeout_ms = max(1, int(timeout_s * 1000))
        cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), host]
    else:
        # Linux/Unix: -c count, -W timeout (seconds)
        cmd = ["ping", "-c", str(count), "-W", str(timeout_s), host]
    output = _run_subprocess(cmd, timeout=timeout_s * max(1, count) + 1)

    if not output:
        return PingResult(status="FAIL", rtt_ms_avg=None, loss_pct=100.0)

    received = 0
    transmitted = count
    rtt_avg = None

    # Generic parse patterns
    m = re.search(r"(\d+) packets transmitted, (\d+) (?:packets )?received", output)
    if m:
        transmitted = int(m.group(1))
        received = int(m.group(2))
    else:
        # Windows style: Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)
        m2 = re.search(r"Sent = (\d+), Received = (\d+), Lost = (\d+)", output)
        if m2:
            transmitted = int(m2.group(1))
            received = int(m2.group(2))

    # RTT avg
    m3 = re.search(r"= [^/]+/([^/]+)/", output)  # e.g., rtt min/avg/max/mdev = 12.345/34.567/...
    if m3:
        try:
            rtt_avg = float(m3.group(1))
        except ValueError:
            rtt_avg = None
    else:
        # Windows: Average = 12ms
        m4 = re.search(r"Average = (\d+)ms", output)
        if m4:
            rtt_avg = float(m4.group(1))

    loss_pct = 0.0 if transmitted == 0 else round(100 - (received / transmitted * 100), 2)
    status = "PASS" if received > 0 else "FAIL"
    return PingResult(status=status, rtt_ms_avg=rtt_avg, loss_pct=loss_pct)


def run_traceroute(host: str, max_hops: int = 15, timeout_s: int = 3) -> Dict:
    if IS_WINDOWS:
        cmd = ["tracert", "-d", "-h", str(max_hops), host]
    else:
        cmd = ["traceroute", "-n", "-m", str(max_hops), host]
    output = _run_subprocess(cmd, timeout=timeout_s * max_hops)
    hops: List[str] = []
    if output:
        for line in output.splitlines():
            line = line.strip()
            # Linux format: hop#  ip  ms ... ; Windows: numeric hop  ip  ms
            m = re.match(r"^\d+\s+([0-9.]+)", line)
            if m:
                hops.append(m.group(1))
    return {"hops": hops, "hop_count": len(hops)}


def _load_offline() -> Dict[str, Dict]:
    if not OFFLINE_FILE.exists():
        raise FileNotFoundError(f"Offline probe data missing: {OFFLINE_FILE}")
    return json.loads(OFFLINE_FILE.read_text())


def validate(target_ip: str, neighbor_map: Dict[str, str], offline: bool = False, with_traceroute: bool = False) -> List[Dict]:
    """Validate reachability for target and neighbors.

    neighbor_map: mapping label->ip
    Returns list of dicts with merged ping/traceroute info.
    """
    results: List[Dict] = []
    ips = {"target": target_ip, **neighbor_map}
    offline_data = _load_offline() if offline else {}

    for label, ip in ips.items():
        if offline:
            data = offline_data.get(ip, {"status": "UNKNOWN", "rtt_ms_avg": None, "loss_pct": 100, "hops": [], "hop_count": 0})
            ping_part = {"status": data.get("status"), "rtt_ms": data.get("rtt_ms_avg"), "loss_pct": data.get("loss_pct")}
            trace_part = {"hops": data.get("hops", []), "hop_count": data.get("hop_count", 0)} if with_traceroute else {}
        else:
            ping_res = run_ping(ip)
            ping_part = {"status": ping_res.status, "rtt_ms": ping_res.rtt_ms_avg, "loss_pct": ping_res.loss_pct}
            trace_part = run_traceroute(ip) if with_traceroute else {}
        combined = {"label": label, "ip": ip, **ping_part, **trace_part}
        results.append(combined)
    return results

__all__ = ["run_ping", "run_traceroute", "validate"]
