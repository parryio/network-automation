import json
from pathlib import Path
import subprocess

def test_batch_offline():
    out_dir = Path('outputs/batch')
    # Remove previous
    if out_dir.exists():
        for p in out_dir.rglob('*'):
            if p.is_file():
                p.unlink()
    cmd = [
        'python', '-m', 'scripts.alarm_triage.batch',
        '--alarms', 'demo/alarms/*.json',
        '--out', str(out_dir),
        '--offline'
    ]
    rc = subprocess.run(cmd, capture_output=True, text=True)
    assert rc.returncode == 0
    # Check files
    assert (out_dir / 'kpi.md').exists()
    assert (out_dir / 'kpi.csv').exists()
    assert (out_dir / 'batch_report.json').exists()
    # Check batch_report.json content
    report = json.loads((out_dir / 'batch_report.json').read_text())
    assert isinstance(report, list) and len(report) >= 1
    for entry in report:
        assert entry['rc'] == 0
        assert isinstance(entry['total_s'], float)
        assert isinstance(entry['validate_s'], float)
        assert entry['success'] is True
