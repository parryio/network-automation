"""CLI entrypoint for DriftGuard policy-as-code drift detection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

from onyxlib.drift.diff import build_diff
from onyxlib.drift.loader import DeviceRecord, load_device_configs, load_inventory
from onyxlib.drift.normalizer import normalize_config
from onyxlib.drift.remediation import ChangePlan, build_change_plan
from onyxlib.drift.report import DeviceSummary, write_report
from onyxlib.drift.rules import RulesEngine, SEVERITY_ORDER


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DriftGuard config drift detection")
    parser.add_argument("--inventory", required=True, help="Path to inventory YAML")
    parser.add_argument("--configs", required=True, help="Directory containing configs")
    parser.add_argument("--rules", required=True, help="Directory containing rules YAML")
    parser.add_argument("--out", required=True, help="Directory for output artifacts")
    parser.add_argument("--render-remediation", action="store_true", help="Render remediation previews")
    parser.add_argument(
        "--fail-on",
        default="critical",
        choices=list(SEVERITY_ORDER.keys()),
        help="Fail CI when drift at or above severity occurs",
    )
    parser.add_argument("--offline", action="store_true", help="Run in offline demonstration mode")
    return parser.parse_args()


def evaluate_device(device: DeviceRecord, engine: RulesEngine, diffs_dir: Path) -> Dict[str, object]:
    running_lines = normalize_config(device.running_config)
    baseline_lines = normalize_config(device.baseline_config or "")
    diff = build_diff(device.name, baseline_lines, running_lines, diffs_dir)
    rule_results = engine.evaluate(device.platform, running_lines)
    return {
        "device": device,
        "diff": diff,
        "rule_results": rule_results,
    }


def main() -> int:
    args = parse_args()
    inventory_entries = load_inventory(Path(args.inventory))
    devices = load_device_configs(inventory_entries, Path(args.configs))
    engine = RulesEngine.from_path(Path(args.rules))

    out_dir = Path(args.out)
    diffs_dir = out_dir / "diffs"
    reports_dir = out_dir

    evaluation: List[Dict[str, object]] = []
    for device in devices:
        evaluation.append(evaluate_device(device, engine, diffs_dir))

    device_to_results: Dict[str, List] = {}
    summaries: List[DeviceSummary] = []
    highest_severity = None

    for item in evaluation:
        device: DeviceRecord = item["device"]
        diff = item["diff"]
        results = item["rule_results"]
        device_to_results[device.name] = results
        failed_rules = [result.rule.rule_id for result in results if not result.passed]
        worst = engine.worst_severity(results)
        if worst and (highest_severity is None or SEVERITY_ORDER[worst] > SEVERITY_ORDER.get(highest_severity, -1)):
            highest_severity = worst
        summaries.append(
            DeviceSummary(
                device=device.name,
                worst_severity=worst,
                failed_rules=failed_rules,
                diff_path=str(diff.diff_path),
                remediation_paths=[],
                diff_lines=diff.line_count,
            )
        )

    remediation_plan: ChangePlan | None = None
    if args.render_remediation:
        remediation_plan = build_change_plan(device_to_results, out_dir)
        by_device: Dict[str, List[str]] = {}
        for snippet in remediation_plan.snippets:
            by_device.setdefault(snippet.device, []).append(snippet.path.name)
        for summary in summaries:
            summary.remediation_paths = by_device.get(summary.device, [])

    write_report(reports_dir, summaries)

    fail_threshold = args.fail_on
    exit_code = 0
    if highest_severity and SEVERITY_ORDER[highest_severity] >= SEVERITY_ORDER[fail_threshold]:
        exit_code = 2

    return exit_code


if __name__ == "__main__":  # pragma: no cover - handled by CLI invocation
    sys.exit(main())
