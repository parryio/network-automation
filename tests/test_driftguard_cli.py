import json
import subprocess
import sys
from pathlib import Path

import yaml


def _write_inventory(path: Path, devices: list[dict]):
    path.write_text(yaml.dump({"devices": devices}))


def test_driftguard_cli_integration(tmp_path: Path):
    inventory_path = tmp_path / "inventory.yml"
    configs_dir = tmp_path / "configs"
    baseline_dir = configs_dir / "baseline"
    baseline_dir.mkdir(parents=True)

    running_config = """
    hostname core-sw01
    ip http server
    ntp server 1.1.1.1
    """
    baseline_config = """
    hostname core-sw01
    ntp server 1.1.1.1
    ntp server 1.0.0.1
    """
    (configs_dir / "core-sw01.running.cfg").write_text(running_config)
    (baseline_dir / "core-sw01.cfg").write_text(baseline_config)

    _write_inventory(
        inventory_path,
        [
            {
                "name": "core-sw01",
                "platform": "cisco_ios",
            }
        ],
    )

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    rules_dir.joinpath("cisco.yml").write_text(
        yaml.dump(
            {
                "platforms": ["cisco_ios"],
                "rules": [
                    {
                        "id": "require-ntp",
                        "severity": "medium",
                        "match": {"contains_lines": ["ntp server 1.0.0.1"]},
                        "remediate": {"commands": ["conf t", "ntp server 1.0.0.1", "end"]},
                    },
                    {
                        "id": "block-http",
                        "severity": "critical",
                        "match": {"not_contains_lines": ["ip http server"]},
                        "remediate": {"commands": ["conf t", "no ip http server", "end"]},
                    },
                ],
            }
        )
    )

    out_dir = tmp_path / "out"
    cmd = [
        sys.executable,
        "-m",
        "scripts.driftguard",
        "--inventory",
        str(inventory_path),
        "--configs",
        str(configs_dir),
        "--rules",
        str(rules_dir),
        "--out",
        str(out_dir),
        "--render-remediation",
        "--fail-on",
        "critical",
        "--offline",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 2, result.stderr

    report_md = out_dir / "drift_report.md"
    metrics_json = out_dir / "metrics.json"
    plan_md = out_dir / "plan.md"
    plan_json = out_dir / "plan.json"
    remediation_dir = out_dir / "remediation"

    assert report_md.exists()
    assert metrics_json.exists()
    assert plan_md.exists()
    assert plan_json.exists()
    remediation_files = list(remediation_dir.glob("*.txt"))
    assert remediation_files, "expected remediation snippets"

    metrics = json.loads(metrics_json.read_text())
    assert metrics["critical_count"] == 1
    assert metrics["drift_count"] == 1
