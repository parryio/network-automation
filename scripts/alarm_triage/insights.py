"""Deterministic heuristic insights: blast radius + next steps.

No additional network probing; derived from alarm, validation results, and inventory site data.
"""
from __future__ import annotations
from typing import Dict, List


def compute_insights(alarm: Dict, validation: List[Dict], site_data: Dict) -> Dict:
    symptom = (alarm.get("symptom") or "").lower()
    target_ip = alarm.get("ip")

    target_entry = None
    neighbor_entries = []
    for entry in validation:
        if entry.get("label") == "target" or entry.get("ip") == target_ip:
            target_entry = entry
        else:
            neighbor_entries.append(entry)

    target_status = (target_entry or {}).get("status")
    neighbor_statuses = [n.get("status") for n in neighbor_entries]

    all_neighbors_pass = all(s == "PASS" for s in neighbor_statuses) if neighbor_statuses else True
    any_neighbor_fail = any(s == "FAIL" for s in neighbor_statuses)

    scope = None
    reason = None

    if target_status == "FAIL" and all_neighbors_pass:
        scope = "Device only (isolated)"
        reason = "Target unreachable while all discovered neighbors responded successfully."
    elif target_status == "FAIL" and any_neighbor_fail:
        scope = "Site or upstream impact (core + neighbor)"
        reason = "Target and at least one neighbor failed validation, suggesting wider impact."
    elif target_status == "PASS" and "bgp neighbor down" in symptom:
        scope = "Routing/session issue (investigate peer)"
        reason = "Target reachable but alarm indicates BGP session problem."
    else:
        scope = "Indeterminate"
        reason = "Pattern not matched; monitor and gather additional telemetry."

    next_steps: List[str] = []
    if scope.startswith("Device only"):
        next_steps.append("Check device power/CPU, mgmt reachability, console access.")
    if scope.startswith("Site or upstream impact"):
        next_steps.append("Check uplink/optics at POP; verify upstream interface status; review LOS/LOF.")
    if "bgp" in symptom:
        next_steps.append("Verify BGP session state, peer reachability, recent route changes/maintenance.")
    if not next_steps:
        next_steps.append("Review recent change logs and monitoring baselines for anomalies.")

    # Ensure max 5 bullets (spec wants 2-5) and at least 2 if possible
    if len(next_steps) == 1:
        next_steps.append("Capture additional diagnostics (interface counters, routing protocol summaries).")
    next_steps = next_steps[:5]

    return {
        "scope": scope,
        "reason": reason,
        "next_steps": next_steps,
    }

__all__ = ["compute_insights"]
