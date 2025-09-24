from pathlib import Path

import yaml

from onyxlib.drift.normalizer import normalize_config
from onyxlib.drift.rules import RulesEngine


def test_rules_engine_parses_platforms(tmp_path: Path):
    rules_file = tmp_path / "rules.yml"
    rules_file.write_text(
        yaml.dump(
            {
                "platforms": ["cisco_ios"],
                "rules": [
                    {
                        "id": "ntp",
                        "severity": "high",
                        "match": {"contains_lines": ["ntp server 1.1.1.1"]},
                        "remediate": {"commands": ["conf t", "ntp server 1.1.1.1", "end"]},
                    }
                ],
            }
        )
    )

    engine = RulesEngine.from_path(tmp_path)
    config_lines = normalize_config("ntp server 1.1.1.1\n")
    results = engine.evaluate("cisco_ios", config_lines)
    assert len(results) == 1
    assert results[0].passed

    other_results = engine.evaluate("juniper_junos", config_lines)
    assert other_results == []


def test_rules_engine_worst_severity(tmp_path: Path):
    rules_file = tmp_path / "rules.yml"
    rules_file.write_text(
        yaml.dump(
            {
                "rules": [
                    {
                        "id": "crit",
                        "severity": "critical",
                        "match": {"contains_lines": ["foo"]},
                        "remediate": {"commands": ["foo"]},
                    },
                    {
                        "id": "low",
                        "severity": "low",
                        "match": {"contains_lines": ["bar"]},
                        "remediate": {"commands": ["bar"]},
                    },
                ]
            }
        )
    )

    engine = RulesEngine.from_path(tmp_path)
    results = engine.evaluate("any", normalize_config("bar\n"))
    # Only low rule passes, critical fails.
    assert engine.worst_severity(results) == "critical"
