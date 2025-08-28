import json
import subprocess
from pathlib import Path
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]

st.title("Alarm Triage Demo")

outputs_dir = REPO_ROOT / "outputs" / "ui"
outputs_dir.mkdir(parents=True, exist_ok=True)


def run_cmd(args):
    proc = subprocess.run(["python", "-m", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.stdout

if st.button("Run A001 Triage"):
    out = run_cmd(["scripts.alarm_triage.triage", "--alarm", "demo/alarms/A001.json", "--out", str(outputs_dir / "A001"), "--offline"])
    st.code(out)

if st.button("Run Batch"):
    out = run_cmd(["scripts.alarm_triage.batch", "--alarms", "demo/alarms/*.json", "--out", str(outputs_dir / "batch"), "--offline"])
    st.code(out)

if st.button("Show KPI"):
    kpi_file = outputs_dir / "batch" / "kpi.md"
    if kpi_file.is_file():
        st.markdown(kpi_file.read_text(encoding="utf-8"))
    else:
        st.warning("Run batch first")
