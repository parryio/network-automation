"""Batch alarm triage CLI."""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Dict, Any, List

import typer

from .triage import process_alarm

app = typer.Typer(add_completion=False)


def process_batch(pattern: str, out_dir: Path, offline: bool = False) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    alarm_files = sorted(glob.glob(pattern))
    results: List[Dict[str, Any]] = []
    for alarm_file in alarm_files:
        alarm_path = Path(alarm_file)
        # Skip auxiliary JSON like probes_offline.json
        try:
            data = json.loads(alarm_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "id" not in data:
            continue
        # Re-write temp alarm file to tmp dir? Not needed; process_alarm will reload.
        single_dir = out_dir / alarm_path.stem
        res = process_alarm(alarm_path, single_dir, offline=offline)
        results.append(res)

    # KPI / summary
    kpi_rows = ["alarm_id,status"]
    for r in results:
        kpi_rows.append(f"{r['alarm']['id']},ok")
    (out_dir / "kpi.csv").write_text("\n".join(kpi_rows) + "\n", encoding="utf-8")
    (out_dir / "kpi.md").write_text(
        f"# Batch KPI\n\nTotal Alarms: {len(results)}\n\n", encoding="utf-8"
    )
    (out_dir / "batch_report.json").write_text(
        json.dumps({"count": len(results), "alarms": [r["alarm"]["id"] for r in results]}, indent=2),
        encoding="utf-8",
    )
    return {"count": len(results), "alarms": [r["alarm"]["id"] for r in results]}


@app.callback(invoke_without_command=True)
def cli(
    alarms: str = typer.Option(..., "--alarms", help="Glob pattern of alarm JSON files"),
    out: str = typer.Option(..., "--out", help="Batch output directory"),
    offline: bool = typer.Option(False, "--offline", help="Use offline demo data"),
):
    """Process a batch of alarms into KPI + reports."""
    summary = process_batch(alarms, Path(out), offline=offline)
    typer.echo(json.dumps(summary, indent=2))


def main():  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
