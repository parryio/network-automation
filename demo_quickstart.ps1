python -m scripts.alarm_triage.triage --alarm demo/alarms/A001.json --out outputs/A001 --offline
python -m scripts.alarm_triage.batch --alarms "demo/alarms/*.json" --out outputs/batch --offline
Write-Host "Artifacts in outputs/"
