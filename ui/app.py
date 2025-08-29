from __future__ import annotations

"""Polished public demo Streamlit UI for alarm triage.

Features:
 - Argument driven (alarms glob, output root)
 - Run triage with spinner + duration timing
 - KPI badges (PASS / FAIL ratio)
 - Results table with human labels
 - Download full artifacts zip
 - JSON structured logs via logging_setup
 - Sanitized output path (must reside within repo root)
 - Redaction of obvious sensitive tokens when displaying snippets
"""

import argparse
import io
import json
import os
import shutil
import sys
import time
import zipfile
import uuid
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

from packaging.version import Version
import streamlit as st

MIN = "1.49.0"
if Version(st.__version__) < Version(MIN):  # pragma: no cover - defensive
    st.error(f"Streamlit ≥ {MIN} required; found {st.__version__}.")
    st.stop()

def rerun():  # simple wrapper now that we pin version
    st.rerun()

def dataframe_kwargs() -> dict:
    return {"width": "stretch"}

REPO_ROOT = Path(__file__).resolve().parents[1]

# Make app robust when run from fresh clone without PYTHONPATH tweaks
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:  # Friendly import check for triage pipeline
    from scripts.alarm_triage.triage import triage_one, triage_batch  # type: ignore
except Exception:  # pragma: no cover - user setup issue
    import streamlit as st  # local import safe
    st.error("Could not import triage pipeline. Ensure you installed requirements and are running from the repo root.")
    st.stop()

# ----------------------------------------------------------------------------------
# Severity ranking helper (transient sorting only)
# ----------------------------------------------------------------------------------
SEV_RANK = {"critical": 3, "major": 2, "minor": 1}

def _sev_rank(s: str) -> int:
    return SEV_RANK.get(str(s).lower(), 0)

# ----------------------------------------------------------------------------------
# Logging setup (if available)
# ----------------------------------------------------------------------------------
try:  # pragma: no cover - optional
    from scripts.alarm_triage.logging_setup import configure_json_logging, log_event
    configure_json_logging()
except Exception:  # pragma: no cover
    def log_event(event: str, **fields):  # type: ignore
        pass

logger = logging.getLogger(__name__)

# Meta directories to always ignore (single source of truth is alarms glob)
EXCLUDE_META = {"batch", "ui", ".cache", ".DS_Store"}

def resolve_alarm_paths(glob_pattern: str) -> List[Path]:
    """Return sorted list of alarm JSON paths from glob that contain an id field."""
    parent = Path(glob_pattern).parent
    name = Path(glob_pattern).name
    paths = sorted(parent.glob(name))
    good: List[Path] = []
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("id") and p.stem not in EXCLUDE_META:
            good.append(p)
    return good

def final_alarm_ids(glob_pattern: str, out_root: Path, include_diagnostics: bool) -> List[str]:
    base_ids = [p.stem for p in resolve_alarm_paths(glob_pattern)]
    if include_diagnostics and (out_root / "probes_offline").exists():
        return base_ids + ["probes_offline"]
    return base_ids


# ----------------------------------------------------------------------------------
# CLI argument parsing (Streamlit passes unknown args after --)
# ----------------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--alarms", default="demo/alarms/*.json", help="Glob of alarm JSON files")
    parser.add_argument("--out", default="outputs", help="Output directory root for triage runs")
    return parser.parse_args()


ARGS = parse_args()


# ----------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------
SENSITIVE_KEYS = {"password", "secret", "community", "token"}


def sanitize_output_dir(out_root: Path) -> Path:
    out_root = out_root.resolve()
    if REPO_ROOT not in out_root.parents and out_root != REPO_ROOT:
        raise ValueError("--out must be inside repository root")
    out_root.mkdir(parents=True, exist_ok=True)
    return out_root


def load_alarm(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("***REDACTED***" if k.lower() in SENSITIVE_KEYS else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def iter_alarm_files(pattern: str) -> List[Path]:
    paths = [Path(p) for p in sorted(Path().glob(pattern))]
    # Filter out helper json that isn't an alarm (no id field)
    good: List[Path] = []
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("id"):
            good.append(p)
    return good


def run_single_alarm(alarm_file: Path, out_root: Path, run_id: Optional[str] = None) -> Dict[str, Any]:
    single_dir = out_root / alarm_file.stem
    start = time.perf_counter()
    log_event("triage_start", alarm=str(alarm_file), run_id=run_id or "")
    result = triage_one(alarm_file, single_dir, offline=True, emit_draft=True, run_id=run_id)
    duration = time.perf_counter() - start
    (single_dir / "duration_s.txt").write_text(f"{duration:.2f}\n", encoding="utf-8")
    log_event("triage_complete", alarm=str(alarm_file), seconds=round(duration, 3), run_id=run_id or "")
    return result


def aggregate_validation(single_dir: Path) -> Dict[str, Any]:
    val_file = single_dir / "validation.json"
    if not val_file.is_file():
        return {}
    try:
        return json.loads(val_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compute_kpis(out_root: Path) -> Dict[str, Any]:
    total = 0
    pass_ct = 0
    fail_ct = 0
    for single in out_root.iterdir():
        if not single.is_dir():
            continue
        val = aggregate_validation(single)
        if not val:
            continue
        total += 1
        status = val.get("status") or val.get("result")
        if status and status.lower() in ("ok", "pass", "success"):
            pass_ct += 1
        else:
            fail_ct += 1
    ratio_pass = f"{pass_ct}/{total}" if total else "0/0"
    ratio_fail = f"{fail_ct}/{total}" if total else "0/0"
    return {"total": total, "pass": pass_ct, "fail": fail_ct, "ratio_pass": ratio_pass, "ratio_fail": ratio_fail}


def build_artifacts_zip(out_root: Path) -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in out_root.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(out_root))
    mem.seek(0)
    return mem.read()


def _build_row(aid: str, alarm_path: Path, out_root: Path) -> Dict[str, Any]:
    """Create one human row combining alarm + validation artifacts. Columns order per spec."""
    try:
        alarm = json.loads(alarm_path.read_text(encoding="utf-8"))
    except Exception:
        alarm = {}
    vpath = out_root / aid / "validation.json"
    try:
        v = json.loads(vpath.read_text(encoding="utf-8")) if vpath.exists() else {}
    except Exception:
        v = {}
    ping_loss = v.get("ping_loss")
    status = v.get("status")
    status_flag = (ping_loss == 0) or (status == "ok")
    if ping_loss == 0:
        ping_human = "0%"
    elif ping_loss in (1, 1.0):
        ping_human = "100%"
    else:
        ping_human = "—"
    last_hop = v.get("traceroute_last_hop") or "—"
    severity = (alarm.get("severity") or "info").lower()
    sev = severity
    node = alarm.get("source") or alarm.get("device") or "—"
    rtt = v.get("rtt_ms")
    # Build row (numeric fields use None for missing to remain Arrow friendly)
    row = {
        "Status": "✅ PASS" if status_flag else "❌ FAIL",
        "Severity": sev,
        "Site": alarm.get("site", "—"),
        "Service": alarm.get("service", "—"),
        "Alarm": aid,
        "Node": node,
        "Symptom": alarm.get("message") or alarm.get("description") or "—",
        "Ping loss": ping_human,
        "RTT (ms)": float(rtt) if rtt is not None else None,
        "Traceroute last hop": last_hop,
        "Artifacts": str((out_root / aid).resolve()),
        "_pass": status_flag,
    "_sev_rank": _sev_rank(severity),
    }
    return row


@st.cache_data(show_spinner=False)
def get_cli_version() -> str:
    try:
        import importlib.metadata as im
        # Not packaged; fallback to git describe or revision time
        return os.getenv("GIT_COMMIT", "dev")
    except Exception:
        return "dev"


# ----------------------------------------------------------------------------------
# Streamlit page config
# ----------------------------------------------------------------------------------
st.set_page_config(page_title="Alarm Triage Demo", layout="wide")
st.title("Alarm Triage Demo – Public Preview")
with st.expander("What this demo shows", expanded=False):
    st.markdown(
        """
        - Deterministic offline triage (synthetic probes seeded by alarm ID)
        - Accessible PASS/FAIL chips (emoji + text)
        - Story-first sort: FAIL → severity → site → node
        - Per-alarm draft modal + downloadable pack
        - Read-only UI (core pipeline owns artifacts)
        - KPIs show counts with percentage deltas
        """
    )
st.caption("Offline-deterministic triage: validate reachability, assemble context, emit ServiceNow draft.")

try:
    OUT_ROOT = sanitize_output_dir(REPO_ROOT / ARGS.out)
except Exception as exc:
    st.error(str(exc))
    st.stop()

ALARM_FILES = resolve_alarm_paths(ARGS.alarms)
if not ALARM_FILES:
    st.warning("No alarms matched the glob. Adjust the pattern and try again.")
    st.stop()
if "selected_alarm" not in st.session_state:
    st.session_state.selected_alarm = str(ALARM_FILES[0])
ss = st.session_state
ss.setdefault("rows", [])
ss.setdefault("ran_once", False)
ss.setdefault("last_scope", None)  # "batch" | "single" | None
ss.setdefault("show_diag", False)         # persisted toggle
ss.setdefault("draft_to_show", None)
ss.setdefault("show_draft_modal", False)

with st.sidebar:
    st.subheader("Controls")
    st.text(f"CLI version: {get_cli_version()}")
    choice = st.selectbox(
        "Alarm",
        options=[str(p) for p in ALARM_FILES],
        index=[str(p) for p in ALARM_FILES].index(st.session_state.selected_alarm),
    )
    if choice != st.session_state.selected_alarm:
        st.session_state.selected_alarm = choice

    # Run triage (batch)
    if st.button("Run triage (all demo alarms)", type="primary"):
        run_id = str(uuid.uuid4())
        ss["run_id"] = run_id
        t0 = time.perf_counter()
        logger.info("ui_run_start", extra={"run_id": run_id, "mode": "batch"})
        with st.spinner("Running triage (batch)..."):
            pattern = str(Path(ARGS.alarms))
            if "*" not in pattern:
                pattern = pattern.replace(".json", "*.json") if pattern.endswith(".json") else pattern + "/*.json"
            triage_batch(pattern, OUT_ROOT, offline=True, emit_draft=True, run_id=run_id)
            glob_path = Path(pattern)
            alarm_paths = sorted(glob_path.parent.glob(glob_path.name))
            alarm_ids = [p.stem for p in alarm_paths if p.is_file()]
            aids = list(alarm_ids)
            if ss.get("show_diag") and (OUT_ROOT / "probes_offline" / "validation.json").exists():
                aids.append("probes_offline")
            built_rows: List[Dict[str, Any]] = []
            for aid in aids:
                alarm_path = next((p for p in alarm_paths if p.stem == aid), None) or Path("/dev/null")
                built_rows.append(_build_row(aid, alarm_path, OUT_ROOT))
            ss["rows"] = built_rows
            ss["ran_once"] = True
            ss["last_scope"] = "batch"
        dt = time.perf_counter() - t0
        logger.info("ui_run_complete", extra={"run_id": run_id, "mode": "batch", "seconds": round(dt,3)})
        st.success("Done.")
        st.rerun()

    # Run triage (single)
    if st.button("Run triage (selected alarm)", type="secondary", disabled=not ss.get("selected_alarm")):
        run_id = str(uuid.uuid4())
        ss["run_id"] = run_id
        t0 = time.perf_counter()
        logger.info("ui_run_start", extra={"run_id": run_id, "mode": "single"})
        with st.spinner("Running triage (selected alarm)..."):
            sel = Path(ss["selected_alarm"])
            aid = sel.stem
            triage_one(sel, OUT_ROOT / aid, offline=True, emit_draft=True, run_id=run_id)
            ss["rows"] = [_build_row(aid, sel, OUT_ROOT)]
            ss["ran_once"] = True
            ss["last_scope"] = "single"
        dt = time.perf_counter() - t0
        logger.info("ui_run_complete", extra={"run_id": run_id, "mode": "single", "seconds": round(dt,3)})
        st.success("Done.")
        st.rerun()

    st.markdown("---")
    if st.button("Clear artifacts"):
        import shutil as _shutil
        _shutil.rmtree(OUT_ROOT, ignore_errors=True)
        ss["rows"] = []
        ss["ran_once"] = False
        ss["last_scope"] = None
        ss["draft_to_show"] = None
        ss["show_draft_modal"] = False
        st.rerun()

# Rows will be built strictly from alarms glob (single source of truth)

# Selected alarm snippet
sel_path = Path(st.session_state.selected_alarm)
alarm_data = redact(load_alarm(sel_path))
with st.expander("Alarm JSON (for reproducibility)", expanded=False):
    st.json(alarm_data)

"""Diagnostics toggle persisted and used to build aids list."""
ss["show_diag"] = st.toggle("Show diagnostics (probes)", value=ss["show_diag"], key="tog_diag")

# Single source of truth: build alarm IDs from glob only; optionally append diagnostics
glob_path = Path(ARGS.alarms)
alarm_paths = sorted(glob_path.parent.glob(glob_path.name))
alarm_ids = [p.stem for p in alarm_paths if p.is_file()]
aids = list(alarm_ids)
if ss.get("show_diag") and (OUT_ROOT / "probes_offline" / "validation.json").exists():
    aids.append("probes_offline")

# Live adjust rows (post-batch run) when diagnostics toggle changes
if ss.get("ran_once") and ss.get("last_scope") == "batch":
    current_ids = [r.get("Alarm") for r in ss.get("rows", [])]
    if sorted(current_ids) != sorted(aids):
        new_rows: List[Dict[str, Any]] = []
        for aid in aids:
            alarm_path = next((p for p in alarm_paths if p.stem == aid), None) or Path("/dev/null")
            new_rows.append(_build_row(aid, alarm_path, OUT_ROOT))
        ss["rows"] = new_rows

def _any_artifacts_exist(out_root: Path) -> bool:
    try:
        return any((d.is_dir() and (d / "validation.json").exists()) for d in out_root.iterdir() if d.is_dir())
    except FileNotFoundError:
        return False

rows: List[Dict[str, Any]] = ss.get("rows", [])
data_ready = ss.get("ran_once") and len(rows) > 0 and OUT_ROOT.exists() and _any_artifacts_exist(OUT_ROOT)

# Gate rendering on data readiness
if not data_ready:
    st.warning("Output directory not found yet. Click **Run triage** to generate artifacts.")
    st.stop()

def _show_draft_modal(aid: str):
    """Render modal with draft preview and downloads."""
    out_dir = OUT_ROOT / aid
    draft_path = out_dir / "draft.md"
    pack_zip = out_dir / f"{aid}_pack.zip"
    validation_path = out_dir / "validation.json"
    alarm_file = None
    # Attempt to locate original alarm json
    base_dir = Path(ARGS.alarms.split("*")[0]) if "*" in ARGS.alarms else Path(ARGS.alarms).parent
    cand = base_dir / f"{aid}.json"
    if cand.is_file():
        alarm_file = cand
    alarm = {}
    if alarm_file:
        try:
            alarm = json.loads(alarm_file.read_text(encoding="utf-8"))
        except Exception:
            alarm = {}
    node = alarm.get("source") or alarm.get("device") or "—"
    severity = alarm.get("severity", "—")
    with st.modal(f"Alarm {aid} draft"):
        st.markdown(f"**Alarm {aid} — {node} — {severity}**")
        # timestamp
        ts = None
        if draft_path.is_file():
            try:
                ts = datetime.fromtimestamp(draft_path.stat().st_mtime, tz=timezone.utc)
            except Exception:
                pass
        duration_s = "—"
        dur_file = out_dir / "duration_s.txt"
        if dur_file.is_file():
            try:
                duration_s = dur_file.read_text().strip()
            except Exception:
                pass
        if ts:
            st.markdown(f"Generated: {ts:%Y-%m-%d %H:%M:%S %Z} • Duration: {duration_s}s")
        else:
            st.markdown(f"Generated: — • Duration: {duration_s}s")
        # draft preview
        if draft_path.is_file():
            st.code(draft_path.read_text(encoding="utf-8"), language="markdown")
            st.download_button("Download draft.md", data=draft_path.read_text(encoding="utf-8"), file_name=f"{aid}_draft.md")
        else:
            st.info("No draft.md present.")
        if pack_zip.is_file():
            st.download_button("Download pack.zip", data=pack_zip.read_bytes(), file_name=pack_zip.name)
        else:
            st.button("Download pack.zip", disabled=True)

#! Compute duration across aids
total_secs = 0.0
for dur_file in OUT_ROOT.glob("*/duration_s.txt"):
    if dur_file.parent.name in aids:
        try:
            total_secs += float(dur_file.read_text().strip())
        except Exception:
            pass

# KPI metrics (counts as value, percent as delta)
n = len(rows)
p = sum(1 for r in rows if r.get("_pass"))
f = n - p
k1, k2, k3 = st.columns(3)
k1.metric("PASS", f"{p}/{n}", f"{int(100 * p / max(n,1))}%")
k2.metric("FAIL", f"{f}/{n}", f"{int(100 * f / max(n,1))}%")
k3.metric("Total Duration (s)", f"{total_secs:.2f}")

# Single results table (only one st.dataframe)
try:
    import pandas as pd  # type: ignore
    df = pd.DataFrame(rows)
    if "RTT (ms)" in df.columns:
        df["RTT (ms)"] = pd.to_numeric(df["RTT (ms)"], errors="coerce")
    if not df.empty:
        df = df.sort_values(
            by=["_pass", "_sev_rank", "Site", "Node"],
            ascending=[True, False, True, True],
            kind="mergesort",
        )
    for col in ["_pass", "_sev_rank"]:
        if col in df.columns:
            df = df.drop(columns=[col])
    ordered_cols = [
        "Status", "Severity", "Site", "Service", "Alarm", "Node",
        "Symptom", "Ping loss", "RTT (ms)", "Traceroute last hop", "Artifacts"
    ]
    df = df[[c for c in ordered_cols if c in df.columns]]
    styler = df.style.format({"RTT (ms)": "{:.1f}"}).format(na_rep="—")
    st.dataframe(styler, width="stretch", hide_index=True)

    # Drafts section
    draft_ids = sorted({r["Alarm"] for r in rows if (OUT_ROOT / str(r["Alarm"]) / "draft.md").exists()})
    if draft_ids:
        st.subheader("Drafts")
        cols = st.columns(3)
        for i, aid in enumerate(draft_ids):
            if cols[i % 3].button(f"View draft: {aid}", key=f"btn_draft_{aid}"):
                ss["draft_to_show"] = aid
                ss["show_draft_modal"] = True
                st.rerun()

    if ss.get("show_draft_modal") and ss.get("draft_to_show"):
        aid = ss["draft_to_show"]
        a_dir = OUT_ROOT / aid
        md_path = a_dir / "draft.md"
        md = md_path.read_text(encoding="utf-8") if md_path.exists() else "# Draft missing"
        with st.modal(f"Draft — {aid}"):
            st.markdown(md)
            c1, c2 = st.columns(2)
            pack_path = a_dir / f"{aid}_pack.zip"
            if pack_path.exists():
                c1.download_button("Download pack.zip", pack_path.read_bytes(), file_name=f"{aid}_pack.zip")
            c2.download_button("Download draft.md", md, file_name=f"{aid}_draft.md")
            if st.button("Close"):
                ss["show_draft_modal"] = False
                ss["draft_to_show"] = None
                st.rerun()
except Exception:  # pragma: no cover - fallback rendering
    st.table([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows])

    if ss.get("show_draft_modal") and ss.get("draft_to_show"):
        aid = ss["draft_to_show"]
        a_dir = OUT_ROOT / aid
        draft_path = a_dir / "draft.md"
        md = draft_path.read_text(encoding="utf-8") if draft_path.exists() else "# Draft missing"
        with st.modal(f"Draft — {aid}"):
            st.markdown(md)
            if st.button("Close"):
                ss["show_draft_modal"] = False
                ss["draft_to_show"] = None
                st.rerun()
    def _dir_stats(p: Path) -> tuple[int, int]:
        files, bytes_ = 0, 0
        if not p.exists():
            return files, bytes_
        for f in p.rglob("*"):
            if f.is_file():
                files += 1
                try:
                    bytes_ += f.stat().st_size
                except Exception:
                    pass
        return files, bytes_

    def _fmt_size(n: int) -> str:
        x = float(n)
        for u in ["B","KB","MB","GB","TB"]:
            if x < 1024:
                return f"{x:.1f} {u}"
            x /= 1024
        return f"{x:.1f} PB"

    if OUT_ROOT.exists() and any(p.is_dir() for p in OUT_ROOT.iterdir()):
        zip_bytes = build_artifacts_zip(OUT_ROOT)
        st.download_button("Download artifacts.zip", data=zip_bytes, file_name="artifacts.zip")
        f_ct, b_ct = _dir_stats(OUT_ROOT)
        st.caption(f"Total artifacts: {f_ct} files • {_fmt_size(b_ct)}")

st.caption("Security: obvious secrets redacted; paths constrained under repo root. Logs structured JSON.")
