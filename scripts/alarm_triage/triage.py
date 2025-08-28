"""Alarm triage core + CLI.

New public API (importable):
    triage_one(alarm_path: Path, out_dir: Path, offline=True, emit_draft=True)
    triage_batch(alarms_glob: str, out_root: Path, offline=True, emit_draft=True)

Legacy (deprecated) API kept as thin shims until next major:
    process_alarm -> triage_one
    process_batch -> triage_batch

CLI (single alarm mode retained for backwards compatibility):
    python -m scripts.alarm_triage.triage --alarm demo/alarms/A001.json --out outputs/A001 --offline
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Iterable, List

import typer

from .context_pack import build_context
from .insights import build_insights, write_insights_md
from .snow_payload import build_snow_payload, write_payload
from .probes import gather_probes

app = typer.Typer(add_completion=False, help="Offline-friendly alarm triage")

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_alarm(alarm_file: Path) -> Dict[str, Any]:
    return json.loads(alarm_file.read_text(encoding="utf-8"))


def _write_audit_line(audit_file: Path, event: str, **extra: Any) -> None:
    record = {"ts": datetime.utcnow().isoformat() + "Z", "event": event}
    record.update(extra)
    with audit_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _zip_pack(out_dir: Path) -> Path:
    pack_path = out_dir / f"{out_dir.name}_pack.zip"
    with zipfile.ZipFile(pack_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in out_dir.rglob("*"):
            if path.is_file() and path != pack_path:
                zf.write(path, path.relative_to(out_dir))
    return pack_path


def _triage_single(alarm_path: Path, out_dir: Path, offline: bool = False, emit_draft: bool = True) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_file = out_dir / "audit.jsonl"
    _write_audit_line(audit_file, "start", alarm=str(alarm_path))

    alarm = _load_alarm(alarm_path)
    _write_audit_line(audit_file, "alarm_loaded", id=alarm.get("id"))

    ctx_dir = out_dir / "context"
    ctx_meta = build_context(alarm, REPO_ROOT, ctx_dir)
    _write_audit_line(audit_file, "context_built", **ctx_meta)

    probes = gather_probes(alarm.get("device", "127.0.0.1"), REPO_ROOT, offline=offline)
    (ctx_dir / "probes.json").write_text(json.dumps(probes, indent=2), encoding="utf-8")
    _write_audit_line(audit_file, "probes_gathered", offline=offline)

    insights = build_insights(alarm)
    _write_audit_line(audit_file, "insights_ready")

    payload = build_snow_payload(alarm, insights)
    write_payload(payload, out_dir / "snow_draft.json")
    write_insights_md(insights, out_dir / "snow_draft.md")
    _write_audit_line(audit_file, "snow_draft_written")

    # validation file
    validation = {"status": "ok", "alarm_id": alarm.get("id"), "offline": offline}
    (out_dir / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    _write_audit_line(audit_file, "validation_written")

    pack_zip = _zip_pack(out_dir)
    _write_audit_line(audit_file, "pack_zipped", pack=str(pack_zip))

    return {
        "alarm": alarm,
        "out_dir": str(out_dir),
        "files": [str(p) for p in out_dir.rglob("*") if p.is_file()],
    }


# ---------------- New exported functions --------------------------------------
def triage_one(alarm_path: Path, out_dir: Path, offline: bool = True, emit_draft: bool = True, run_id: str | None = None):
    """Triage a single alarm JSON file into an output directory.

    Parameters mirror legacy process_alarm with extended args for future.
    """
    return _triage_single(alarm_path, out_dir, offline=offline, emit_draft=emit_draft)


def triage_batch(alarms_glob: str, out_root: Path, offline: bool = True, emit_draft: bool = True, run_id: str | None = None):
    """Triage all alarms matching a glob into per-alarm subdirectories under out_root."""
    paths = sorted(Path().glob(alarms_glob))
    results: List[Dict[str, Any]] = []
    for p in paths:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict) or not data.get("id"):
            continue
        out_dir = out_root / p.stem
        results.append(_triage_single(p, out_dir, offline=offline, emit_draft=emit_draft))
    return results


@app.callback(invoke_without_command=True)
def cli(
    alarm: str = typer.Option(..., "--alarm", help="Path to alarm JSON file"),
    out: str = typer.Option(..., "--out", help="Output directory"),
    offline: bool = typer.Option(False, "--offline", help="Use offline demo data"),
):
    """Process a single alarm. No subcommand required (simpler for CI)."""
    if alarm and out:  # invoked directly
        alarm_path = Path(alarm)
        out_dir = Path(out)
    result = triage_one(alarm_path, out_dir, offline=offline)
    typer.echo(json.dumps({"status": "ok", "files": len(result["files"])}, indent=2))


def main():  # pragma: no cover - entrypoint
    app()


if __name__ == "__main__":  # pragma: no cover
    main()

# --- Back-compat shims (do not remove until next major) -----------------------
from pathlib import Path as _Path  # noqa: E402

def process_alarm(alarm_path, out_dir, offline: bool = True, emit_draft: bool = True):  # type: ignore
    """Compat shim: old name -> triage_one"""
    return triage_one(_Path(alarm_path), _Path(out_dir), offline=offline, emit_draft=emit_draft)

def process_batch(alarms_glob, out_root, offline: bool = True, emit_draft: bool = True):  # type: ignore
    """Compat shim: old name -> triage_batch"""
    return triage_batch(alarms_glob, _Path(out_root), offline=offline, emit_draft=emit_draft)
