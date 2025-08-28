from pathlib import Path
from scripts.alarm_triage.triage import process_alarm


def test_single_alarm_offline(tmp_path: Path):
    out_dir = tmp_path / "A001"
    res = process_alarm(Path("demo/alarms/A001.json"), out_dir, offline=True)
    expected = {"validation.json", "snow_draft.json", "snow_draft.md", "audit.jsonl"}
    files = {p.name for p in out_dir.iterdir() if p.is_file()}
    assert expected.issubset(files)
    # context directory
    ctx = out_dir / "context"
    assert (ctx / "prior_incidents.json").is_file()
    assert (ctx / "config.txt").is_file()
    assert (ctx / "site001.txt").is_file()
    # pack zip
    assert any(p.name.endswith("_pack.zip") for p in out_dir.iterdir())
    # insights keywords
    snow_md = (out_dir / "snow_draft.md").read_text(encoding="utf-8")
    assert "Blast Radius" in snow_md
    assert "Suggested Next Steps" in snow_md
