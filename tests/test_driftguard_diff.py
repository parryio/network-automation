from pathlib import Path

from onyxlib.drift.diff import build_diff


def test_build_diff_writes_file(tmp_path: Path):
    out = tmp_path / "diffs"
    result = build_diff(
        device="device1",
        baseline_lines=["line1", "line2"],
        running_lines=["line1", "line3"],
        out_dir=out,
    )
    assert result.diff_path.exists()
    content = result.diff_path.read_text()
    assert "-line2" in content
    assert "+line3" in content
    assert result.line_count == 2
