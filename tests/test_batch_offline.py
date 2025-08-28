from pathlib import Path
from scripts.alarm_triage.batch import process_batch


def test_batch_offline(tmp_path: Path):
    out_dir = tmp_path / "batch"
    summary = process_batch("demo/alarms/*.json", out_dir, offline=True)
    assert summary["count"] >= 4
    assert (out_dir / "kpi.csv").is_file()
    assert (out_dir / "kpi.md").is_file()
    assert (out_dir / "batch_report.json").is_file()
    # each alarm subdir has validation
    for alarm_id in summary["alarms"]:
        assert (out_dir / alarm_id / "validation.json").is_file()
