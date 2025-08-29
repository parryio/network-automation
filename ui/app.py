from __future__ import annotations

"""Demo-ready Streamlit UI for alarm triage (stable, single-pass interactions).

Key behaviors (as per one-shot hardening prompt):
 - Deterministic path normalization from repo root
 - No st.rerun() loops; buttons execute and table refreshes immediately
 - Diagnostics (probes) toggle derives ids strictly from alarms glob
 - Arrow / PyArrow friendly DataFrame coercions + pretty display
 - Per-row "View draft" modal opens in same run (no intermediate rerun)
 - Output directory constrained under repo root
"""

import argparse
import glob
import io
import json
import os
import sys
import time
import zipfile
import uuid
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np  # numeric sanitation
import pandas as pd  # dataframe operations

from packaging.version import Version
import streamlit as st

HAS_MODAL = hasattr(st, "modal")

MIN = "1.49.0"
if Version(st.__version__) < Version(MIN):  # pragma: no cover - defensive
    st.error(f"Streamlit ≥ {MIN} required; found {st.__version__}.")
    st.stop()

# ---------------------------------------------------------------------------
# Path normalization helpers (always relative to repo root)
# ---------------------------------------------------------------------------
from pathlib import Path as _PathAlias  # noqa: E402
ROOT = Path(__file__).resolve().parents[1]

def to_root(p: str | Path) -> Path:
    q = Path(p)
    return q if q.is_absolute() else (ROOT / q)

REPO_ROOT = ROOT

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

# ---------------------------------------------------------------------------
# DataFrame numeric sanitation helpers
# ---------------------------------------------------------------------------
def as_int64_nullable(series: pd.Series) -> pd.Series:
    """Coerce heterogeneous numeric-ish series to pandas nullable Int64.

    Non (int|float) or non-finite values become <NA>.
    Values are rounded (banker's rounding per pandas .round) before cast.
    """
    def _keep_num(v):
        return v if isinstance(v, (int, float, np.integer, np.floating)) and np.isfinite(v) else None
    s = series.map(_keep_num)
    s = pd.to_numeric(s, errors="coerce")  # float64 w/ NaN
    return s.round().astype("Int64")

# Meta directories to always ignore (single source of truth is alarms glob)
EXCLUDE_META = {"batch", "ui", ".cache", ".DS_Store"}

def _normalize_glob(g: str) -> str:
    """Return absolute glob string rooted at REPO_ROOT if relative."""
    p = Path(g)
    if not p.is_absolute():
        return str((REPO_ROOT / g).resolve())
    return str(p)


def resolve_alarm_paths(glob_pattern: str) -> List[Path]:
    """Return sorted list of alarm JSON paths from glob (relative paths resolved to repo root)."""
    glob_pattern = _normalize_glob(glob_pattern)
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
    ns, _ = parser.parse_known_args()
    return ns

ARGS = parse_args()

# Normalize & sanitize paths immediately
ALARMS_GLOB_RAW = ARGS.alarms
OUT_ROOT = to_root(ARGS.out).resolve()
ALARMS_GLOB = str(to_root(ALARMS_GLOB_RAW))
if ROOT not in OUT_ROOT.parents and OUT_ROOT != ROOT:  # safety guard
    st.error("Output must be inside repo root")
    st.stop()
OUT_ROOT.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------
SENSITIVE_KEYS = {"password", "secret", "community", "token"}


def sanitize_output_dir(out_root: Path) -> Path:  # retained for back-compat use elsewhere
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
    """Return alarm JSON Paths strictly from glob (no meta injection)."""
    abs_glob = str(to_root(pattern))
    paths = sorted(glob.glob(abs_glob))
    good: List[Path] = []
    for p in paths:
        P = Path(p)
        if not P.is_file():
            continue
        try:
            data = json.loads(P.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("id"):
            good.append(P)
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
    if not isinstance(rtt, (int, float)):
        rtt = None
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

ALARM_FILES = iter_alarm_files(ALARMS_GLOB)
if not ALARM_FILES:
    st.warning("No alarms matched the glob. Tip: if you launched from `ui/`, use `../demo/alarms/*.json` or pass absolute paths.")

ss = st.session_state
if "selected_alarm" not in ss and ALARM_FILES:
    ss.selected_alarm = str(ALARM_FILES[0])
ss.setdefault("rows", [])
ss.setdefault("last_run_ts", None)

def collect_rows(alarm_paths: List[Path], include_diag: bool) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for p in alarm_paths:
        aid = p.stem
        rows.append(_build_row(aid, p, OUT_ROOT))
    if include_diag:
        diag = ROOT / "demo" / "alarms" / "probes_offline.json"
        if diag.exists():
            rows.append(_build_row("probes_offline", diag, OUT_ROOT))
    return rows

with st.sidebar:
    st.subheader("Controls")
    st.text(f"CLI version: {get_cli_version()}")
    if ALARM_FILES:
        prev = ss.get("selected_alarm_path")
        try:
            idx = ALARM_FILES.index(Path(prev)) if prev else 0
        except Exception:
            idx = 0
        selected_alarm_path: Path = st.selectbox(
            "Alarm",
            options=ALARM_FILES,
            index=idx,
            format_func=lambda p: p.stem,
            key="selected_alarm_path",
        )
        ss.selected_alarm = str(selected_alarm_path)
        try:
            rel = selected_alarm_path.resolve().relative_to(ROOT)
        except Exception:
            rel = selected_alarm_path
        st.caption(f"File: {rel}")
    else:
        st.selectbox("Alarm", options=["(none)"] , index=0, disabled=True)

    show_diag = st.toggle("Show diagnostics (probes)", value=bool(ss.get("show_diag", False)))
    ss["show_diag"] = show_diag

    # Batch triage
    if st.button("Run triage (all demo alarms)", type="primary", disabled=not ALARM_FILES):
        run_id = str(uuid.uuid4())
        t0 = time.perf_counter()
        with st.spinner("Running triage (all alarms)..."):
            triage_batch(ALARMS_GLOB, OUT_ROOT, offline=True, emit_draft=True, run_id=run_id)
        alarm_paths = [Path(p) for p in sorted(glob.glob(ALARMS_GLOB)) if Path(p).is_file()]
        ss["rows"] = collect_rows(alarm_paths, include_diag=show_diag)
        ss["last_run_ts"] = time.time()
        st.toast("Triage complete", icon="✅")

    # Single alarm triage
    if st.button("Run triage (selected alarm)", type="secondary", disabled=not ss.get("selected_alarm")):
        sel = Path(ss.selected_alarm)
        run_id = str(uuid.uuid4())
        with st.spinner(f"Running triage ({sel.stem})..."):
            triage_one(sel, OUT_ROOT / sel.stem, offline=True, emit_draft=True, run_id=run_id)
        ss["rows"] = collect_rows([sel], include_diag=False)
        ss["last_run_ts"] = time.time()
        st.toast("Triage complete", icon="✅")

    st.markdown("---")
    if st.button("Clear artifacts"):
        import shutil as _shutil
        _shutil.rmtree(OUT_ROOT, ignore_errors=True)
        ss["rows"] = []
        ss["last_run_ts"] = time.time()
        st.toast("Cleared", icon="🧹")

# Rows will be built strictly from alarms glob (single source of truth)

# Selected alarm snippet
sel_path = Path(st.session_state.selected_alarm)
alarm_data = redact(load_alarm(sel_path))
with st.expander("Alarm JSON (for reproducibility)", expanded=False):
    st.json(alarm_data)

show_diag = bool(ss.get("show_diag"))

def _any_artifacts_exist(out_root: Path) -> bool:
    try:
        return any((d.is_dir() and (d / "validation.json").exists()) for d in out_root.iterdir() if d.is_dir())
    except FileNotFoundError:
        return False

rows: List[Dict[str, Any]] = ss.get("rows", [])
data_ready = len(rows) > 0 and OUT_ROOT.exists() and _any_artifacts_exist(OUT_ROOT)

# Gate rendering KPI/table only when data ready (but keep page interactive)
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
    title = f"Alarm {aid} draft"
    if HAS_MODAL:
        ctx = st.modal(title)
    else:
        ctx = st.expander(title, expanded=True)
    with ctx:
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

alarm_ids_for_duration = {r["Alarm"] for r in rows} if data_ready else set()
total_secs = 0.0
for dur_file in OUT_ROOT.glob("*/duration_s.txt"):
    if dur_file.parent.name in alarm_ids_for_duration:
        try:
            total_secs += float(dur_file.read_text().strip())
        except Exception:
            pass

if data_ready:
    n = len(rows)
    p_ct = sum(r.get("_pass", False) for r in rows)
    f_ct = n - p_ct
    k1, k2 = st.columns(2)
    k1.metric("PASS", f"{p_ct}/{n}", f"{int(100 * p_ct / max(n,1))}%")
    k2.metric("FAIL", f"{f_ct}/{n}", f"{int(100 * f_ct / max(n,1))}%")
    import pandas as pd  # type: ignore
    df = pd.DataFrame(rows)
    # Normalize Alarm (ID only) and Artifacts (repo-relative path)
    from pathlib import Path as _PathNorm
    def _alarm_label(val: str) -> str:
        p = _PathNorm(str(val))
        return p.stem if p.suffix == ".json" else p.name
    def _short_path(p: str) -> str:
        try:
            return str(_PathNorm(p).resolve().relative_to(ROOT))
        except Exception:
            return str(p)
    if "Alarm" in df.columns:
        df["Alarm"] = df["Alarm"].apply(_alarm_label)
    if "Artifacts" in df.columns:
        df["Artifacts"] = df["Artifacts"].apply(_short_path)
    if "Alarm" not in df.columns and "Artifacts" in df.columns:
        df["Alarm"] = df["Artifacts"].apply(lambda p: _PathNorm(str(p)).name)
    # Type coercions (Arrow safe)
    if "RTT (ms)" in df.columns:
        # Robust coercion (sanitizes non-numeric to <NA>)
        df["RTT (ms)"] = as_int64_nullable(df["RTT (ms)"])
    for c in ["Severity", "Site", "Service", "Node", "Status"]:
        if c in df.columns:
            df[c] = df[c].astype("string")
    # Sort (fail first, severity rank desc)
    if not df.empty:
        df = df.sort_values(by=["_pass", "_sev_rank", "Site", "Node"], ascending=[True, False, True, True], kind="mergesort")
    # Drop transient cols for display
    display_df = df.drop(columns=[c for c in ["_pass", "_sev_rank"] if c in df.columns])
    # Column config for prettier numeric display
    try:
        from streamlit import column_config as colcfg  # lazy import for backward compat
        table_cfg = {"RTT (ms)": colcfg.NumberColumn("RTT (ms)", format="%d")}
        st.dataframe(display_df, width="stretch", column_config=table_cfg, hide_index=True)
    except Exception:  # fallback if older Streamlit
        st.dataframe(display_df, width="stretch")

    # Per-row draft buttons (hashed keys + modal fallback)
    def _row_key(row) -> str:
        base = f"{row.get('Alarm')}|{row.get('Artifacts')}|{row.get('Node')}"
        return hashlib.sha1(base.encode()).hexdigest()[:10]

    def _render_draft(row: dict, k: str):
        from pathlib import Path as _P
        aid = str(row.get("Alarm"))
        pack_dir = _P(str(row.get("Artifacts", "")))
        if not pack_dir.is_absolute():  # resolve relative to ROOT
            pack_dir = ROOT / pack_dir
        # Prefer draft.md, fallback to snow_draft.md
        md_file = pack_dir / "draft.md"
        if not md_file.exists():
            alt = pack_dir / "snow_draft.md"
            if alt.exists():
                md_file = alt
        if md_file.exists():
            try:
                st.markdown(md_file.read_text(encoding="utf-8"))
            except Exception:
                st.info("Draft could not be read.")
        else:
            st.info("No draft available.")
        # Pack zip
        zip_file = None
        for cand in pack_dir.glob("*_pack.zip"):
            zip_file = cand
            break
        if zip_file and zip_file.exists():
            st.download_button(
                "Download artifacts.zip",
                data=zip_file.read_bytes(),
                file_name=zip_file.name,
                key=f"dl_{k}",
            )

    for _, row in display_df.reset_index(drop=True).iterrows():
        k = _row_key(row)
        aid = str(row.get("Alarm", "unknown"))
        if st.button("View draft", key=f"view_{k}"):
            title = f"Draft: {aid}"
            if HAS_MODAL:
                with st.modal(title, key=f"modal_{k}"):
                    _render_draft(row, k)
            else:
                with st.expander(title, expanded=True):
                    _render_draft(row, k)
else:
    # Provide contextual warning when no data is yet present.
    if not ALARM_FILES:
        st.warning("No alarms matched the glob. Tip: if you launched from `ui/`, use `../demo/alarms/*.json` or pass absolute paths.")
    else:
        st.warning("No triage artifacts yet. Use the sidebar buttons to run triage.")

st.caption("Security: obvious secrets redacted; paths constrained under repo root. Logs structured JSON.")
