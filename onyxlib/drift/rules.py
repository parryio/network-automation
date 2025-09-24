"""Rules-as-code engine for DriftGuard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import yaml

from .normalizer import join_lines

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class Rule:
    rule_id: str
    severity: str
    contains_lines: Sequence[str]
    not_contains_lines: Sequence[str]
    remediation: Sequence[str]
    platforms: Optional[Sequence[str]] = None

    def applies_to(self, platform: str) -> bool:
        if not self.platforms:
            return True
        return platform in self.platforms

    def evaluate(self, config_lines: Sequence[str]) -> "RuleResult":
        config_blob = join_lines(config_lines)
        missing: List[str] = []
        unexpected: List[str] = []

        for line in self.contains_lines:
            if line not in config_blob:
                missing.append(line)
        for line in self.not_contains_lines:
            if line in config_blob:
                unexpected.append(line)

        passed = not missing and not unexpected
        reason_parts: List[str] = []
        if missing:
            reason_parts.append(f"missing: {', '.join(missing)}")
        if unexpected:
            reason_parts.append(f"unexpected: {', '.join(unexpected)}")
        reason = "; ".join(reason_parts)

        return RuleResult(rule=self, passed=passed, reason=reason)


@dataclass
class RuleResult:
    rule: Rule
    passed: bool
    reason: str

    @property
    def severity(self) -> str:
        return self.rule.severity

    def is_failure(self) -> bool:
        return not self.passed


class RulesEngine:
    """Loads and evaluates DriftGuard rules."""

    def __init__(self, rules: Sequence[Rule]):
        self._rules = list(rules)

    @classmethod
    def from_path(cls, rules_path: Path) -> "RulesEngine":
        rules: List[Rule] = []
        rules_dir = Path(rules_path)
        for path in sorted(rules_dir.glob("*.yml")) + sorted(rules_dir.glob("*.yaml")):
            rules.extend(_parse_rules_file(path))
        return cls(rules)

    def evaluate(self, platform: str, config_lines: Sequence[str]) -> List[RuleResult]:
        return [rule.evaluate(config_lines) for rule in self._rules if rule.applies_to(platform)]

    def worst_severity(self, results: Sequence[RuleResult]) -> Optional[str]:
        failing = [result.severity for result in results if result.is_failure()]
        if not failing:
            return None
        return max(failing, key=lambda sev: SEVERITY_ORDER.get(sev, -1))


def _parse_rules_file(path: Path) -> List[Rule]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Rules file {path} must be a mapping")
    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list):
        raise ValueError(f"Rules file {path} must contain a 'rules' list")
    platforms = data.get("platforms")
    platforms_list = list(platforms) if isinstance(platforms, (list, tuple)) else None

    parsed: List[Rule] = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            raise ValueError(f"Rule entries must be mappings in {path}")
        rule_id = str(raw.get("id"))
        severity = str(raw.get("severity", "medium")).lower()
        if severity not in SEVERITY_ORDER:
            raise ValueError(f"Rule {rule_id} has invalid severity '{severity}'")
        match_block = raw.get("match", {})
        contains = []
        not_contains = []
        if isinstance(match_block, dict):
            contains = list(match_block.get("contains_lines", []) or [])
            not_contains = list(match_block.get("not_contains_lines", []) or [])
        remediate_block = raw.get("remediate", {})
        commands: Sequence[str] = []
        if isinstance(remediate_block, dict):
            commands = list(remediate_block.get("commands", []) or [])
        rule_platforms = platforms_list
        if isinstance(raw.get("platforms"), (list, tuple)):
            rule_platforms = list(raw.get("platforms"))
        parsed.append(
            Rule(
                rule_id=rule_id,
                severity=severity,
                contains_lines=contains,
                not_contains_lines=not_contains,
                remediation=commands,
                platforms=rule_platforms,
            )
        )
    return parsed
