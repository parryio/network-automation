#!/usr/bin/env bash
set -euo pipefail
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.backup_configs --offline-from demo/configs --out configs
python -m scripts.audit_baseline --configs configs/latest --report reports/baseline_report.csv
python -m scripts.push_change --offline --before demo/configs/edge-rtr01.cfg --name edge-rtr01 \
  --ntp "1.1.1.1,1.0.0.1" --banner "Authorized access only" \
  --disable-http --fix-ssh --timestamps \
  --diffs diffs --write-after --after-out configs/after_demo
python -m scripts.audit_baseline --configs configs/after_demo --report reports/after_baseline_report.csv
echo "Artifacts ready: reports/, diffs/, configs/after_demo/"
