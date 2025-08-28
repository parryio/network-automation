# Run: streamlit run ui/streamlit_app.py
"""Streamlit mini-UI wrapper for Alarm Triage.

This is a thin layer over the existing CLI (scripts.alarm_triage.triage). It
invokes the CLI via subprocess each time one of the action buttons is pressed
and then surfaces relevant generated artifacts in the UI.

Design notes:
- Read-only; no device writes.
- Defaults to offline mode for deterministic behavior.
- Each button actually runs the same full pipeline; buttons just control which
  sections are emphasized after execution.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
import sys
import textwrap
import traceback

import streamlit as st

try:  # Optional
    import pandas as pd  # type: ignore
    HAS_PANDAS = True
except Exception:
    HAS_PANDAS = False

APP_ROOT = Path(__file__).resolve().parent
REPO_ROOT = APP_ROOT.parent
DEMO_ALARMS_DIR = REPO_ROOT / 'demo' / 'alarms'
DEFAULT_OFFLINE = True
DEFAULT_TRACEROUTE = False

st.set_page_config(page_title="Alarm Triage", layout="wide")

st.title("Alarm Triage Mini-UI (Read-Only)")
st.caption("Wraps the CLI: scripts.alarm_triage.triage")
st.markdown(
    "Use the sidebar to pick an alarm, then run validation / context build / SNOW draft generation. Each button runs the full triage; sections below display available artifacts."
)

# Sidebar controls
with st.sidebar:
    st.header("Inputs")
    alarm_files = sorted([p for p in DEMO_ALARMS_DIR.glob('*.json')])
    if not alarm_files:
        st.error("No alarm files found in demo/alarms")
        st.stop()

    if 'selected_alarm' not in st.session_state:
        st.session_state.selected_alarm = alarm_files[0].name
    if 'out_dir' not in st.session_state:
        # Derive alarm_id from file
        try:
            data = json.loads(alarm_files[0].read_text())
            st.session_state.out_dir = f"outputs/{data.get('alarm_id','A001')}"
        except Exception:
            st.session_state.out_dir = "outputs/A001"

    selected_alarm_name = st.selectbox(
        'Alarm JSON', [p.name for p in alarm_files], index=[p.name for p in alarm_files].index(st.session_state.selected_alarm)
    )
    st.session_state.selected_alarm = selected_alarm_name

    # Output directory input
    out_dir_input = st.text_input('Output directory', st.session_state.out_dir)
    st.session_state.out_dir = out_dir_input

    offline = st.checkbox('Offline mode', value=DEFAULT_OFFLINE)
    with_tr = st.checkbox('With traceroute', value=DEFAULT_TRACEROUTE)

    st.markdown('---')
    st.markdown('Buttons run the same CLI; they simply focus the display below:')
    colb1, colb2, colb3 = st.columns(3)
    with colb1:
        btn_validate = st.button('Validate')
    with colb2:
        btn_context = st.button('Build Context')
    with colb3:
        btn_snow = st.button('Create SNOW Draft')

# Determine which display emphasis
focus = None
if btn_validate:
    focus = 'validate'
elif btn_context:
    focus = 'context'
elif btn_snow:
    focus = 'snow'

alarm_path = DEMO_ALARMS_DIR / st.session_state.selected_alarm
out_dir = Path(st.session_state.out_dir)
out_dir.mkdir(parents=True, exist_ok=True)

cli_cmd = [sys.executable, '-m', 'scripts.alarm_triage.triage', '--alarm', str(alarm_path), '--out', str(out_dir)]
if offline:
    cli_cmd.append('--offline')
if with_tr:
    cli_cmd.append('--with-traceroute')

run_logs = None
rc = None
if focus:  # Only run when a button pressed
    with st.spinner(f"Running triage ({' '.join(cli_cmd)}) ..."):
        try:
            proc = subprocess.run(cli_cmd, capture_output=True, text=True, timeout=25)
            rc = proc.returncode
            run_logs = proc.stdout + '\n' + proc.stderr
        except subprocess.TimeoutExpired:
            rc = -1
            run_logs = 'Timed out executing triage CLI.'
        except Exception as e:  # pragma: no cover - UI path
            rc = -2
            run_logs = f"Exception: {e}\n" + traceback.format_exc()

if focus and run_logs is not None:
    with st.expander("Run logs"):
        st.code(run_logs or '(no output)')
    if rc != 0:
        st.error(f"CLI exited with code {rc}. Some artifacts may be missing.")

# Helper to load JSON safely

def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

validation_file = out_dir / 'validation.json'
context_dir = out_dir / 'context'
snow_md = out_dir / 'snow_draft.md'
zip_files = list(out_dir.glob('*_pack.zip'))

# Validation section
if not focus or focus == 'validate':
    st.subheader('Validation Results')
    if validation_file.exists():
        val = load_json(validation_file) or []
        if HAS_PANDAS:
            import pandas as _pd  # type: ignore
            st.dataframe(_pd.DataFrame(val))
        else:
            st.table(val)
    else:
        st.info('validation.json not found yet.')

# Context section
if not focus or focus == 'context':
    st.subheader('Context Pack')
    if context_dir.exists():
        # Diagram preference: overlay, png, svg, txt
        overlay = None
        png = None
        svg = None
        txt = None
        for p in context_dir.iterdir():
            if p.name == 'diagram_overlay.png':
                overlay = p
            elif p.suffix.lower() == '.png' and not png:
                png = p
            elif p.suffix.lower() == '.svg' and not svg:
                svg = p
            elif p.suffix.lower() == '.txt' and not txt:
                txt = p
        diagram_shown = False
        if overlay and overlay.exists():
            st.image(str(overlay), caption='Diagram Overlay')
            diagram_shown = True
        elif png and png.exists():
            st.image(str(png), caption=png.name)
            diagram_shown = True
        elif svg and svg.exists():
            # Streamlit supports SVG via markdown embedding
            st.markdown(svg.read_text(), unsafe_allow_html=True)
            diagram_shown = True
        elif txt and txt.exists():
            st.code(txt.read_text(), language='text')
            diagram_shown = True
        if not diagram_shown:
            st.info('No diagram found.')

        # Prior incidents
        pi = context_dir / 'prior_incidents.json'
        if pi.exists():
            incidents = load_json(pi) or []
            if incidents:
                st.markdown('**Prior Incidents**')
                if HAS_PANDAS:
                    import pandas as _pd  # type: ignore
                    st.dataframe(_pd.DataFrame(incidents))
                else:
                    st.table(incidents)
        else:
            st.info('prior_incidents.json missing')

        # Config snippet
        cfg = context_dir / 'config.txt'
        if cfg.exists():
            st.markdown('**Config Snippet**')
            st.code(cfg.read_text(), language='text')
        else:
            st.info('config.txt missing')
    else:
        st.info('Context directory not created yet.')

# SNOW Draft section
if not focus or focus == 'snow':
    st.subheader('ServiceNow Draft')
    if snow_md.exists():
        st.markdown(snow_md.read_text())
    else:
        st.info('snow_draft.md not found')

# Download section for ZIP
if zip_files:
    zf = zip_files[0]
    with open(zf, 'rb') as f:
        st.download_button('Download Pack ZIP', data=f, file_name=zf.name, mime='application/zip')


# Batch KPI tab/expander
st.markdown('---')
st.subheader('Batch KPI')
batch_out = Path('outputs/batch')
if st.button('Run Batch KPI (offline)'):
    import subprocess
    cmd = [sys.executable, '-m', 'scripts.alarm_triage.batch', '--alarms', 'demo/alarms/*.json', '--out', str(batch_out), '--offline']
    with st.spinner('Running batch triage...'):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        st.code(proc.stdout + '\n' + proc.stderr)
if (batch_out / 'kpi.md').exists():
    st.markdown((batch_out / 'kpi.md').read_text())
if (batch_out / 'kpi.csv').exists():
    with open(batch_out / 'kpi.csv', 'rb') as f:
        st.download_button('Download KPI CSV', data=f, file_name='kpi.csv', mime='text/csv')
if (batch_out / 'batch_report.json').exists():
    with open(batch_out / 'batch_report.json', 'rb') as f:
        st.download_button('Download Batch Report JSON', data=f, file_name='batch_report.json', mime='application/json')
st.caption('Read-only; offline mode uses canned probe data for deterministic output.')
