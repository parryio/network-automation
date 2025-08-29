"""Single / batch alarm triage CLI (core artifact owner).

Artifacts (owned here, NOT by UI):
 - validation.json
 - snow_draft.json / snow_draft.md
 - draft.md (short markdown draft via servicenow.make_draft)
 - context/ pack + audit.jsonl
"""

from __future__ import annotations

import json
import glob
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

import typer

from .context_pack import build_context
from .insights import build_insights, write_insights_md
from .snow_payload import build_snow_payload, write_payload
from .probes import gather_probes
from .servicenow import make_draft
from .mock_validation import synth_metrics

app = typer.Typer(add_completion=False, help="Offline-friendly alarm triage")

REPO_ROOT = Path(__file__).resolve().parents[2]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_alarm(alarm_file: Path) -> Dict[str, Any]:
    return json.loads(alarm_file.read_text(encoding="utf-8"))


def _write_audit_line(audit_file: Path, event: str, **extra: Any) -> None:
    record = {"ts": _utc_now_iso(), "event": event}
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


def triage_one(
    alarm_path: Path,
    out_dir: Path,
    offline: bool = False,
    emit_draft: bool = True,
    run_id: str | None = None,
) -> Dict[str, Any]:
    """Process a single alarm deterministically.

    Ownership: all artifacts produced here (UI must be read-only).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_file = out_dir / "audit.jsonl"
    _write_audit_line(audit_file, "start", alarm=str(alarm_path), **({"run_id": run_id} if run_id else {}))

    alarm = _load_alarm(alarm_path)
    _write_audit_line(audit_file, "alarm_loaded", id=alarm.get("id"), **({"run_id": run_id} if run_id else {}))

    ctx_dir = out_dir / "context"
    ctx_meta = build_context(alarm, REPO_ROOT, ctx_dir)
    _write_audit_line(audit_file, "context_built", **ctx_meta, **({"run_id": run_id} if run_id else {}))

    probes = gather_probes(alarm.get("device", "127.0.0.1"), REPO_ROOT, offline=offline)
    (ctx_dir / "probes.json").write_text(json.dumps(probes, indent=2), encoding="utf-8")
    _write_audit_line(audit_file, "probes_gathered", offline=offline, **({"run_id": run_id} if run_id else {}))

    insights = build_insights(alarm)
    _write_audit_line(audit_file, "insights_ready", **({"run_id": run_id} if run_id else {}))

    payload = build_snow_payload(alarm, insights)
    write_payload(payload, out_dir / "snow_draft.json")
    write_insights_md(insights, out_dir / "snow_draft.md")
    _write_audit_line(audit_file, "snow_draft_written", **({"run_id": run_id} if run_id else {}))

    # validation (include ping_loss placeholder deterministic 0)
    validation = {
        "alarm_id": alarm.get("id"),
        "offline": offline,
    }
    # When offline (demo) inject synthetic realistic metrics
    if offline:
        validation.update(synth_metrics(str(alarm.get("id"))))
    (out_dir / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    _write_audit_line(audit_file, "validation_written", **({"run_id": run_id} if run_id else {}))

    if emit_draft:
        draft_text = make_draft(alarm, validation)
        (out_dir / "draft.md").write_text(draft_text, encoding="utf-8")
        _write_audit_line(audit_file, "draft_written", **({"run_id": run_id} if run_id else {}))

    pack_zip = _zip_pack(out_dir)
    _write_audit_line(audit_file, "pack_zipped", pack=str(pack_zip), **({"run_id": run_id} if run_id else {}))

    return {
        "alarm": alarm,
        "out_dir": str(out_dir),
        "files": [str(p) for p in out_dir.rglob("*") if p.is_file()],
    }


def triage_batch(
    pattern: str,
    out_dir: Path,
    offline: bool = False,
    emit_draft: bool = True,
    run_id: str | None = None,
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    alarm_files = sorted(glob.glob(pattern))
    results: List[Dict[str, Any]] = []
    for alarm_file in alarm_files:
        ap = Path(alarm_file)
        try:
            data = json.loads(ap.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or "id" not in data:
            continue
        single_dir = out_dir / ap.stem
        res = triage_one(ap, single_dir, offline=offline, emit_draft=emit_draft, run_id=run_id)
        results.append(res)
    return {"count": len(results), "alarms": [r["alarm"].get("id") for r in results]}


@app.callback(invoke_without_command=True)
def cli(
    alarm: str = typer.Option(None, "--alarm", help="Path to single alarm JSON file"),
    alarms: str = typer.Option(None, "--alarms", help="Glob pattern for batch triage"),
    out: str = typer.Option(..., "--out", help="Output directory (single or batch root)"),
    offline: bool = typer.Option(False, "--offline", help="Use offline demo data"),
    emit_draft: bool = typer.Option(True, "--emit-draft/--no-emit-draft", help="Write draft.md artifact"),
):
    """Process a single alarm or a batch (core artifact ownership)."""
    if alarm and alarms:
        raise typer.BadParameter("Specify either --alarm or --alarms, not both")
    if not alarm and not alarms:
        raise typer.BadParameter("One of --alarm or --alarms is required")
    if alarm:
        result = triage_one(Path(alarm), Path(out), offline=offline, emit_draft=emit_draft)
        typer.echo(json.dumps({"status": "ok", "files": len(result["files"])}, indent=2))
    else:
        summary = triage_batch(alarms, Path(out), offline=offline, emit_draft=emit_draft)
        typer.echo(json.dumps(summary, indent=2))


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
