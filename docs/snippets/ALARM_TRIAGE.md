# Alarm Triage Demo

This demo showcases a fully offline, deterministic alarm triage flow:

1. Load an alarm JSON (demo/alarms/A001.json).
2. Assemble context (prior incidents, static config, site diagram, probe data).
3. Generate insights (blast radius + suggested next steps).
4. Produce a ServiceNow style draft (JSON + Markdown) and an audit log.
5. Package everything into a zip for attachment / archival purposes.

Batch mode processes multiple alarms and emits KPI artifacts (CSV + Markdown + JSON report).

All operations are read-only and remain inside the `outputs/` directory.

Run a single alarm triage:

```bash
python -m scripts.alarm_triage.triage --alarm demo/alarms/A001.json --out outputs/A001 --offline
```

Run batch triage:

```bash
python -m scripts.alarm_triage.batch --alarms "demo/alarms/*.json" --out outputs/batch --offline
```
