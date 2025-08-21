from __future__ import annotations
import re
import csv
from pathlib import Path
import typer
from rich import print
from rich.table import Table
import yaml

app = typer.Typer(help="Audit configs against a simple baseline.")

def load_baseline(path: Path) -> dict:
    return yaml.safe_load(path.read_text())

def read_configs(configs_dir: Path) -> list[tuple[str, str]]:
    files = sorted(p for p in configs_dir.glob("*.cfg"))
    return [(p.stem, p.read_text(encoding="utf-8", errors="ignore")) for p in files]

def check_profile(cfg: str, profile: dict) -> dict:
    findings = {"pass": True, "details": []}

    def must_include(s: str) -> None:
        if s not in cfg:
            findings["pass"] = False
            findings["details"].append(f"MISSING: {s}")

    def must_not_include(s: str) -> None:
        if s in cfg:
            findings["pass"] = False
            findings["details"].append(f"FORBID: {s}")

    for s in profile.get("must_include", []):
        must_include(s)
    for s in profile.get("must_not_include", []):
        must_not_include(s)

    for item in profile.get("regex_require", []):
        pat = re.compile(item["pattern"], re.MULTILINE)
        if not pat.search(cfg):
            findings["pass"] = False
            findings["details"].append(f"MISSING_RE: {item['pattern']}")

    for item in profile.get("regex_forbid", []):
        pat = re.compile(item["pattern"], re.MULTILINE)
        if pat.search(cfg):
            findings["pass"] = False
            findings["details"].append(f"FORBID_RE: {item['pattern']}")

    return findings

@app.command()
def main(
    configs: Path = typer.Option(Path("configs/latest"), "--configs", help="Folder of .cfg files"),
    baseline: Path = typer.Option(Path("baseline.yaml"), "--baseline", help="Baseline rules YAML"),
    profile: str = typer.Option("cisco_ios", "--profile", help="Profile key under baseline.profiles"),
    report: Path = typer.Option(Path("reports/baseline_report.csv"), "--report", help="CSV report path"),
):
    if not configs.exists():
        raise typer.BadParameter(f"Configs dir not found: {configs}")
    rules = load_baseline(baseline)
    prof = rules.get("profiles", {}).get(profile)
    if not prof:
        raise typer.BadParameter(f"Profile not found in baseline: {profile}")

    report.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    table = Table(title=f"Baseline Audit – {profile}")
    table.add_column("Device")
    table.add_column("Status")
    table.add_column("Details")

    for dev, text in read_configs(configs):
        res = check_profile(text, prof)
        status = "PASS" if res["pass"] else "FAIL"
        table.add_row(dev, "[green]PASS" if res["pass"] else "[red]FAIL", "; ".join(res["details"]))
        rows.append({"device": dev, "status": status, "details": " | ".join(res["details"])})

    with report.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["device", "status", "details"])
        w.writeheader()
        w.writerows(rows)

    print(table)
    print(f"Report written to: [bold]{report}[/bold]")

if __name__ == "__main__":
    app()
