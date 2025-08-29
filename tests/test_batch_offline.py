from pathlib import Path
from scripts.alarm_triage.triage import triage_batch


def test_batch_offline(tmp_path: Path):
    out_dir = tmp_path / "batch"
    summary = triage_batch("demo/alarms/*.json", out_dir, offline=True, emit_draft=True)
    assert summary["count"] >= 4
    # each alarm subdir has validation
    for alarm_id in summary["alarms"]:
        single = out_dir / alarm_id
        assert (single / "validation.json").is_file()
        assert (single / "draft.md").is_file()
