#!/usr/bin/env bash
set -euo pipefail
python -m scripts.alarm_triage.triage --alarms "demo/alarms/*.json" --out outputs/batch --offline --emit-draft || \
python -m scripts.alarm_triage.triage --alarm demo/alarms/A001.json --out outputs/A001 --offline
echo "Artifacts in outputs/" >&2
