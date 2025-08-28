param()
$ErrorActionPreference = 'Stop'
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m scripts.alarm_triage.triage --alarm demo/alarms/A001.json --out outputs/A001 --offline
python -m scripts.alarm_triage.batch --alarms "demo/alarms/A00*.json" --out outputs/batch --offline
streamlit run ui/streamlit_app.py
