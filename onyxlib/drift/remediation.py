"""Utilities for building remediation previews."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

from .rules import RuleResult


@dataclass
class RemediationSnippet:
    device: str
    commands: Sequence[str]
    path: Path
    rule_ids: Sequence[str]


@dataclass
class ChangePlan:
    plan_md: Path
    plan_json: Path
    snippets: List[RemediationSnippet]


def build_remediation_snippets(device: str, results: Sequence[RuleResult], out_dir: Path) -> List[RemediationSnippet]:
    snippets: List[RemediationSnippet] = []
    remediation_dir = out_dir / "remediation"
    remediation_dir.mkdir(parents=True, exist_ok=True)

    for result in results:
        if result.passed or not result.rule.remediation:
            continue
        commands = list(result.rule.remediation)
        path = remediation_dir / f"{device}__{result.rule.rule_id}.txt"
        header = [f"! remediation for {device} rule {result.rule.rule_id}"]
        path.write_text("\n".join(header + list(commands)) + "\n")
        snippets.append(
            RemediationSnippet(
                device=device,
                commands=commands,
                path=path,
                rule_ids=[result.rule.rule_id],
            )
        )
    return snippets


def build_change_plan(device_results: Dict[str, Sequence[RuleResult]], out_dir: Path) -> ChangePlan:
    """Create a markdown and JSON change plan for remediation."""

    plan_dir = Path(out_dir)
    plan_dir.mkdir(parents=True, exist_ok=True)

    all_snippets: List[RemediationSnippet] = []
    for device, results in device_results.items():
        all_snippets.extend(build_remediation_snippets(device, results, plan_dir))

    plan_md = plan_dir / "plan.md"
    plan_json = plan_dir / "plan.json"

    lines: List[str] = ["# DriftGuard Change Plan", ""]
    json_payload: Dict[str, List[Dict[str, object]]] = {"devices": []}

    for snippet in all_snippets:
        lines.append(f"## {snippet.device}")
        lines.append("")
        lines.append("```")
        for command in snippet.commands:
            lines.append(command)
        lines.append("```")
        lines.append("")
        json_payload["devices"].append(
            {
                "device": snippet.device,
                "rules": list(snippet.rule_ids),
                "commands": list(snippet.commands),
                "path": str(snippet.path),
            }
        )

    plan_md.write_text("\n".join(lines) + "\n")
    import json

    plan_json.write_text(json.dumps(json_payload, indent=2))

    return ChangePlan(plan_md=plan_md, plan_json=plan_json, snippets=all_snippets)
