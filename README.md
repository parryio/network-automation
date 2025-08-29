![demo](https://github.com/parryio/network-automation/actions/workflows/ci.yml/badge.svg)

[![demo](https://github.com/parryio/network-automation/actions/workflows/ci.yml/badge.svg)](https://github.com/parryio/network-automation/actions/workflows/ci.yml)

**Download demo artifacts:** See the “demo-artifacts” attachment in the latest successful run under **Actions → demo**. It includes:
- `reports/baseline_report.csv`
- `reports/after_baseline_report.csv`
- `diffs/` (unified diffs)
- `configs/after_demo/` (post-change configs)

**One-click offline run:** `./demo.sh` (Unix) or `./demo.ps1` (Windows).

```
One-shot Copilot prompt (paste into Copilot Chat at repo root)
You are helping me implement “Week 1: CI + Artifacts” for my network-automation repo.

Context:
- Python/Netmiko offline demo proving backups, baseline audit, safe change (NTP + banner) with diffs & idempotency.
- I want GitHub Actions to run the offline demo on every push/PR and publish artifacts.

Tasks (create/modify exactly as specified):
1) Create .github/workflows/ci.yml with a single job “demo” on ubuntu-latest, Python 3.11. Steps:
  - checkout
  - setup-python
  - create venv, pip install -r requirements.txt
  - run the offline demo in this exact order:
    a) python -m scripts.backup_configs --offline-from demo/configs --out configs
    b) python -m scripts.audit_baseline --configs configs/latest --report reports/baseline_report.csv
    c) python -m scripts.push_change --offline --before demo/configs/edge-rtr01.cfg --name edge-rtr01 --ntp "1.1.1.1,1.0.0.1" --banner "Authorized access only" --disable-http --fix-ssh --timestamps --diffs diffs --write-after --after-out configs/after_demo
    d) python -m scripts.audit_baseline --configs configs/after_demo --report reports/after_baseline_report.csv
  - upload artifacts named demo-artifacts including: reports/*.csv, diffs/**, configs/after_demo/**
  - add concurrency to cancel in-progress runs for same ref

2) Add two helper scripts at repo root:
  - demo.sh (bash) and demo.ps1 (PowerShell) that mirror the exact commands above and set -euo / $ErrorActionPreference=Stop.

3) Append to .gitignore:
  .venv/, __pycache__/, *.pyc, .pytest_cache/, reports/, diffs/, configs/after_demo/, configs/latest/

4) Update README.md near the top:
  - Insert a CI badge pointing to actions/workflows/ci.yml
  - Add a short “Download demo artifacts” section listing reports/*.csv, diffs/, configs/after_demo/
  - Mention one-click run: ./demo.sh (Unix) or .\demo.ps1 (Windows)

Constraints:
- Do not refactor existing scripts or change their CLI.
- Assume Python 3.11 only.
- Keep commands exactly as written.
- Keep the workflow filename as .github/workflows/ci.yml.

Verification checklist (write it as a PR description):
- Workflow runs on push/PR and succeeds on a clean checkout.
- Artifacts include both CSVs, diffs, and after_demo configs.
- Local one-click scripts work on Windows and Unix.

Push flow (copy/paste)
git checkout -b feat/ci-artifacts
mkdir -p .github/workflows
# add files from above here…
git add .github/workflows/ci.yml demo.sh demo.ps1 .gitignore README.md
git commit -m "CI: run offline demo on push/PR and publish artifacts"
git push -u origin feat/ci-artifacts
# Open PR on GitHub
```

# Network Automation

<<<<<<< HEAD
## Scope & Purpose
- **Scope:** Three small Python/Netmiko automations: config **backup**, **baseline audit**, and **safe change** (NTP + banner), with an **offline demo** (no hardware) that produces real artifacts (CSV, diffs, after-config).
- **Purpose:** Show practical network automation that is **reproducible**, **safe** (dry-run + diffs), and **idempotent**—the essentials for change control.
=======
Practical network automation scripts (Python/Netmiko) for three real tasks + an offline alarm triage demo UI:
>>>>>>> 8cc0126 (UI overhaul)

## What’s included
- `scripts/backup_configs.py` – backups (parallel)
- `scripts/audit_baseline.py` – baseline checks (YAML) → CSV
- `scripts/push_change.py` – safe change with `--dry-run`, diffs, and **offline write-after**  
  - Offline fixers: `--disable-http`, `--fix-ssh`, `--timestamps`

<<<<<<< HEAD
## Offline demo (no hardware)
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
=======
## Quickstart (UI)

Exactly 3 commands (Python 3.11+):

```bash
git clone https://github.com/parryio/network-automation.git
cd network-automation && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m streamlit run ui/app.py -- --alarms "demo/alarms/*.json" --out outputs
```

Then click Run triage. Artifacts land under `outputs/<ALARM_ID>/` with `validation.json`, `snow_draft.*`, `draft.md`, `context/` and a ZIP pack.

> Artifacts are produced by the core triage pipeline; the UI never writes them.

Demo shows deterministic synthetic metrics (seeded by Alarm ID) plus accessible PASS/FAIL chips; core pipeline owns artifacts and the UI is strictly read‑only.
KPIs show counts with percentages (as metric deltas). Diagnostics (probes) are hidden by default—use the toggle to show.

We target Streamlit ≥ 1.49 and use a tiny compat layer (`utils/streamlit_compat.py`) so no deprecated APIs appear in the codebase.
Requires Streamlit ≥ 1.49.0; deprecated APIs removed and replaced with stable equivalents.
Demo validation metrics (ping loss / RTT / traceroute hops) are deterministic synthetic values seeded by alarm ID for repeatable screenshots.

### Before / After (Alarm → Draft)

Raw alarm (excerpt):

```json
{ "id": "A001", "device": "edge-rtr01", "site": "site001", "severity": 3 }
```

Generated draft (excerpt):

```markdown
# ServiceNow Draft
**Alarm**: A001
**Device**: edge-rtr01
**Site**: site001
**Validation Status**: ok
```

Batch mode:
```bash
make demo  # processes all demo alarms into outputs/batch
```

## Legacy Quickstart (Windows PowerShell)

```powershell
# create venv and install deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
>>>>>>> 8cc0126 (UI overhaul)
pip install -r requirements.txt

python -m scripts.backup_configs --offline-from demo/configs --out configs
python -m scripts.audit_baseline --configs configs/latest --report reports/baseline_report.csv

python -m scripts.push_change --offline --before demo/configs/edge-rtr01.cfg --name edge-rtr01 \
  --ntp "1.1.1.1,1.0.0.1" --banner "Authorized access only" \
  --disable-http --fix-ssh --timestamps \
  --diffs diffs --write-after --after-out configs/after_demo

python -m scripts.audit_baseline --configs configs/after_demo --report reports/after_baseline_report.csv
