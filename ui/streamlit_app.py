from __future__ import annotations
import json, subprocess, sys, warnings
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import streamlit as st

# Optional but nice if installed (do not add as hard dep)
try:  # pragma: no cover - optional
    import pandas as pd  # type: ignore  # noqa
except Exception:  # pragma: no cover
    pd = None  # graceful fallback

# Optional: suppress noisy runpy runtime warnings but still show stderr
warnings.filterwarnings("ignore", message=".*runpy.*", category=RuntimeWarning)

REPO_ROOT = Path(__file__).resolve().parents[1]
ALARM_DIR = REPO_ROOT / "demo" / "alarms"

st.set_page_config(page_title="Alarm Triage Demo", layout="wide")
st.title("Alarm Triage → ServiceNow Draft (Read-Only)")
st.caption("One command: validate reachability → assemble context → create a SNOW draft. Cross-platform. Offline-deterministic.")

# --------------------------------------------------------------------------------------
# CLI Detection
# --------------------------------------------------------------------------------------
@dataclass
class CLIMeta:
    style: str  # "argparse" | "click"
    supports_traceroute: bool
    help_text: str = ""


def _probe(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # pragma: no cover
        return 1, "", str(e)


@st.cache_resource(show_spinner=False)
def detect_cli() -> CLIMeta:
    base = [sys.executable, "-m", "scripts.alarm_triage.triage"]
    # Try click style first (subcommand 'run')
    rc_click, out_click, err_click = _probe(base + ["run", "--help"])  # click often supports 'run'
    if rc_click == 0:
        text = out_click + err_click
        supports = "--with-traceroute" in text
        return CLIMeta(style="click", supports_traceroute=supports, help_text=text)
    # Fallback to argparse style
    rc_arg, out_arg, err_arg = _probe(base + ["--help"])
    text = out_arg + err_arg
    supports = "--with-traceroute" in text
    style = "argparse" if rc_arg == 0 else "argparse"  # default to argparse if uncertain
    return CLIMeta(style=style, supports_traceroute=supports, help_text=text)


def build_cmd(alarm_path: str, out_dir: str, offline: bool, want_trace: bool, meta: CLIMeta) -> List[str]:
    cmd: List[str] = [sys.executable, "-m", "scripts.alarm_triage.triage"]
    if meta.style == "click":
        cmd += ["run"]
    cmd += ["--alarm", alarm_path, "--out", out_dir]
    if offline:
        cmd.append("--offline")
    if want_trace and meta.supports_traceroute:
        cmd.append("--with-traceroute")
    return cmd


def build_batch_cmd(alarms_glob: str, out_dir: str, offline: bool, meta: CLIMeta) -> List[str]:
    cmd: List[str] = [sys.executable, "-m", "scripts.alarm_triage.batch"]
    if meta.style == "click":
        cmd += ["run"]
    cmd += ["--alarms", alarms_glob, "--out", out_dir]
    if offline:
        cmd.append("--offline")
    return cmd


def run_cli(cmd: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    rc, out, err = proc.returncode, proc.stdout, proc.stderr
    with st.expander("Run logs", expanded=False):
        st.write("Command:", " ".join(cmd))
        if out:
            st.code(out)
        if err:
            st.code(err)
    return rc, out, err


# --------------------------------------------------------------------------------------
# Helpers (safe / defensive)
# --------------------------------------------------------------------------------------
def _read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _normalize_validation(obj) -> list[dict]:
    if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
        return obj  # type: ignore
    return []


def _pass_fail_counts(rows):
    ok = 0
    fail = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("status") == "PASS":
            ok += 1
        else:
            fail += 1
    return ok, fail


def _latency_avg(rows):
    vals = []
    for r in rows:
        if isinstance(r, dict):
            v = r.get("rtt_ms")
            if isinstance(v, (int, float)):
                vals.append(v)
    return round(sum(vals) / len(vals), 1) if vals else None


def _status_style(df):  # pragma: no cover - UI detail
    def style_row(s):
        color = ["#16a34a" if v == "PASS" else "#dc2626" for v in s]
        return [f"color:{c}; font-weight:600" for c in color]
    return df.style.apply(style_row, subset=["status"], axis=0)


# --------------------------------------------------------------------------------------
# Sidebar controls & actions
# --------------------------------------------------------------------------------------
alarms = sorted(ALARM_DIR.glob("*.json"))
if not alarms:
    st.error("No alarms found in demo/alarms/")
    st.stop()

if "alarm" not in st.session_state:
    st.session_state.alarm = str(alarms[0])
if "outdir" not in st.session_state:
    st.session_state.outdir = str(REPO_ROOT / "outputs" / Path(st.session_state.alarm).stem)
if "triage_rc" not in st.session_state:
    st.session_state.triage_rc = None
if "triage_failed" not in st.session_state:
    st.session_state.triage_failed = False

cli_meta = detect_cli()

with st.sidebar:
    st.header("Controls")
    st.caption(f"CLI style: {cli_meta.style}; traceroute: {'yes' if cli_meta.supports_traceroute else 'no'}")
    sel = st.selectbox(
        "Alarm JSON",
        options=[str(a) for a in alarms],
        index=[str(a) for a in alarms].index(st.session_state.alarm),
    )
    if sel != st.session_state.alarm:
        st.session_state.alarm = sel
        st.session_state.outdir = str(REPO_ROOT / "outputs" / Path(sel).stem)
    st.session_state.outdir = st.text_input("Output directory", st.session_state.outdir)
    offline = st.checkbox("Offline mode", value=True)
    want_trace = st.checkbox("With traceroute", value=False)

    st.markdown("---")
    run_col, batch_col = st.columns(2)
    if run_col.button("Run Triage"):
        if want_trace and not cli_meta.supports_traceroute:
            st.info("Traceroute not supported by this CLI; running without it.")
        cmd = build_cmd(st.session_state.alarm, st.session_state.outdir, offline, want_trace, cli_meta)
        rc, _stdout, _stderr = run_cli(cmd)
        st.session_state.triage_rc = rc
        st.session_state.triage_failed = rc != 0
        if rc != 0:
            st.error(f"CLI exited {rc}")
    if batch_col.button("Run Batch"):
        batch_cmd = build_batch_cmd(str(ALARM_DIR / "*.json"), str(REPO_ROOT / "outputs" / "batch"), offline, cli_meta)
        brc, _b_stdout, _b_stderr = run_cli(batch_cmd)
        if brc != 0:
            st.error(f"Batch CLI exited {brc}")

# If last triage failed, avoid parsing artifacts (soft fail)
if st.session_state.triage_failed:
    st.stop()

# --------------------------------------------------------------------------------------
# Load artifacts safely
# --------------------------------------------------------------------------------------
out_root = Path(st.session_state.outdir)
alarm_data = _read_json(Path(st.session_state.alarm)) or {}
site = alarm_data.get("site", "site") if isinstance(alarm_data, dict) else "site"

validation = _normalize_validation(_read_json(out_root / "validation.json"))
snow_md_path = out_root / "snow_draft.md"
snow_json = _read_json(out_root / "snow_draft.json") or {}
ctx_dir = out_root / "context"

# --------------------------------------------------------------------------------------
# Summary metrics
# --------------------------------------------------------------------------------------
sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
ok, fail = _pass_fail_counts(validation)
avg = _latency_avg(validation)
sum_col1.metric("Hosts validated", f"{len(validation)}")
sum_col2.metric("Reachable", f"{ok}")
sum_col3.metric("Unreachable", f"{fail}")
sum_col4.metric("Avg RTT (ms)", f"{avg if avg is not None else '—'}")

# --------------------------------------------------------------------------------------
# Tabs
# --------------------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["Validation", "Context", "ServiceNow Draft", "Batch KPI"])

with tab1:
    st.subheader("Validation Results")
    kpi_col1, kpi_col2 = st.columns(2)
    kpi_col1.success(f"PASS: {ok}")
    kpi_col2.error(f"FAIL: {fail}") if fail else kpi_col2.write(f"FAIL: {fail}")
    if validation:
        if pd:
            df = pd.DataFrame(validation)
            keep_cols = [c for c in ["label", "ip", "status", "rtt_ms", "loss_pct", "hop_count"] if c in df.columns]
            df = df[keep_cols]
            st.dataframe(_status_style(df), use_container_width=True)
        else:
            st.table(validation)
    else:
        if not (out_root / "validation.json").exists():
            st.info("validation.json not found (did the run fail?).")
        else:
            st.info("No validation entries.")

with tab2:
    st.subheader("Context Pack")
    if not ctx_dir.exists():
        st.info("No context/ yet. Run triage.")
    else:
        overlay = ctx_dir / "diagram_overlay.png"
        png = ctx_dir / f"{site}.png"
        svg = ctx_dir / f"{site}.svg"
        txt = ctx_dir / f"{site}.txt"
        if overlay.exists():
            st.image(str(overlay), caption="diagram_overlay.png")
        elif png.exists():
            st.image(str(png), caption=f"{site}.png")
        elif svg.exists():
            st.image(str(svg), caption=f"{site}.svg")
        elif txt.exists():
            st.code(txt.read_text(), language="text")
        else:
            st.info("No diagram artifact.")

        pi = ctx_dir / "prior_incidents.json"
        if pi.exists():
            st.markdown("**Prior Incidents**")
            data = _read_json(pi) or []
            if pd and isinstance(data, list):
                st.dataframe(pd.DataFrame(data), use_container_width=True)
            else:
                st.table(data)
        else:
            st.info("prior_incidents.json missing")

        cfg = ctx_dir / "config.txt"
        if cfg.exists():
            st.markdown("**Config Snippet**")
            st.code(cfg.read_text(), language="text")
        else:
            st.info("config.txt missing")

with tab3:
    st.subheader("ServiceNow Draft")
    if snow_md_path.exists():
        st.markdown(snow_md_path.read_text())
    else:
        st.info("snow_draft.md not found yet.")

    zips = list(out_root.glob("*_pack.zip"))
    if zips:
        z = zips[0]
        with z.open("rb") as f:
            st.download_button("Download ZIP Artifact", data=f.read(), file_name=z.name)
    else:
        st.info("ZIP not created yet.")

    if isinstance(snow_json, dict) and snow_json:
        with st.expander("Draft JSON", expanded=False):
            st.json(snow_json)

with tab4:
    st.subheader("Batch KPI")
    batch_dir = REPO_ROOT / "outputs" / "batch"
    kpi_md = batch_dir / "kpi.md"
    kpi_csv = batch_dir / "kpi.csv"
    report_json = batch_dir / "batch_report.json"

    if kpi_md.exists():
        st.markdown(kpi_md.read_text())
    else:
        if report_json.exists():
            data = _read_json(report_json) or {}
            st.write({k: data.get(k) for k in ("total", "pass", "fail", "duration_s") if k in (data or {})})
        else:
            st.info("Run Batch to generate kpi.md or batch_report.json.")

    cols = st.columns(2)
    if kpi_csv.exists():
        cols[0].download_button("Download kpi.csv", data=kpi_csv.read_bytes(), file_name="kpi.csv")
    if report_json.exists():
        cols[1].download_button("Download batch_report.json", data=report_json.read_bytes(), file_name="batch_report.json")

# End of resilient UI
