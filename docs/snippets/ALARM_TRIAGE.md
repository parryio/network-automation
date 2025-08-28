# Alarm Triage Quickstart (v0.2.1)

```
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python -m scripts.alarm_triage.triage --alarm demo/alarms/A001.json --out outputs/A001 --offline
python -m scripts.alarm_triage.batch --alarms "demo/alarms/A00*.json" --out outputs/batch --offline
streamlit run ui/streamlit_app.py  # optional UI
```

The Alarm Triage module converts an alarm JSON into: (1) validation.json (ping / optional traceroute), (2) a context pack (diagram, prior incidents, config snippet), (3) ServiceNow draft payload (snow_draft.json + snow_draft.md), and (4) a zipped artifact. It's read-only and supports deterministic offline mode used by CI.

Example input alarm (demo/alarms/A001.json):
```json
{ "alarm_id": "A001", "severity": "critical", "site": "site001", "device": "rtr-site001-core", "ip": "10.1.1.1", "timestamp": "2025-08-20T14:22:31Z", "symptom": "ICMP Unreachable; BGP neighbor down" }
```

Excerpt of generated markdown (snow_draft.md):
```
# ServiceNow Draft: A001
Alarm A001 ICMP Unreachable; BGP neighbor down on rtr-site001-core (site001)
## Validation Results
- target (10.1.1.1): FAIL
- sw-site001-edge01 (10.1.2.11): PASS
- sw-site001-edge02 (10.1.2.12): PASS
```

## Why It Matters
Automated triage cuts MTTR by pre-packaging: live reachability evidence, prior incident context, config snippet, blast-radius assessment, and recommended next steps. Batch KPIs (p50/p95 run-time & success rate) help SRE teams monitor reliability and performance of the triage process over time.

## Additional Demo Alarms
- A002: Link down (neighbor focus)
- A003: BGP flap (target reachable, session issue)
- A004: Power event (critical isolated failure)

## 90‑Second Demo Script
1. Run A001 offline triage (see quickstart).
2. Open `outputs/A001/snow_draft.md` – highlight Blast Radius & Suggested Next Steps.
3. Batch run: `python -m scripts.alarm_triage.batch --alarms "demo/alarms/A00*.json" --out outputs/batch --offline`.
4. Open `outputs/batch/kpi.md` – show p50/p95 & success rate.
5. Launch UI: `streamlit run ui/streamlit_app.py` – demo Validate & Batch KPI.

Notes: All outputs land under --out (e.g., outputs/A001). CI publishes artifacts for Linux/Windows runners. No device configuration changes are made and no secrets are required.
