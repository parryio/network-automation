"""Rendering of DriftGuard reports and metrics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import json

from .rules import SEVERITY_ORDER


@dataclass
class DeviceSummary:
    device: str
    worst_severity: str | None
    failed_rules: List[str]
    diff_path: str
    remediation_paths: List[str]
    diff_lines: int


@dataclass
class DriftReport:
    markdown_path: Path
    json_path: Path
    metrics_path: Path
    device_summaries: List[DeviceSummary]

    def to_dict(self) -> Dict[str, object]:
        return {
            "devices": [summary.__dict__ for summary in self.device_summaries],
        }


def render_markdown(summaries: Sequence[DeviceSummary]) -> str:
    lines = ["# DriftGuard Report", ""]
    lines.append("| Device | Worst Severity | Failed Rules | Diff | Remediation | Diff Lines |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for summary in summaries:
        rules_text = ", ".join(summary.failed_rules) if summary.failed_rules else "-"
        remediation_text = ", ".join(summary.remediation_paths) if summary.remediation_paths else "-"
        lines.append(
            f"| {summary.device} | {summary.worst_severity or '-'} | {rules_text} | {summary.diff_path} | {remediation_text} | {summary.diff_lines} |"
        )
    return "\n".join(lines) + "\n"


def write_report(out_dir: Path, summaries: Sequence[DeviceSummary]) -> DriftReport:
    out_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = out_dir / "drift_report.md"
    json_path = out_dir / "drift_report.json"
    metrics_path = out_dir / "metrics.json"

    markdown_path.write_text(render_markdown(summaries))
    json_path.write_text(json.dumps({"devices": [summary.__dict__ for summary in summaries]}, indent=2))

    drift_count = sum(1 for summary in summaries if summary.failed_rules)
    critical_count = sum(1 for summary in summaries if summary.worst_severity == "critical")
    mean_drift = 0.0
    if summaries:
        mean_drift = sum(summary.diff_lines for summary in summaries) / len(summaries)

    metrics = {
        "drift_count": drift_count,
        "critical_count": critical_count,
        "mean_drift_lines": round(mean_drift, 2),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2))

    return DriftReport(
        markdown_path=markdown_path,
        json_path=json_path,
        metrics_path=metrics_path,
        device_summaries=list(summaries),
    )
