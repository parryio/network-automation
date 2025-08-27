import json
from pathlib import Path
import importlib

from scripts.alarm_triage import triage as triage_mod


def test_offline_triage(tmp_path: Path):
    out_dir = Path('outputs/A001')  # use specified path per spec
    if out_dir.exists():
        # clean previous
        for p in sorted(out_dir.rglob('*'), reverse=True):
            if p.is_file():
                p.unlink()
            else:
                p.rmdir()
    argv = [
        '--alarm', 'demo/alarms/A001.json',
        '--out', str(out_dir),
        '--offline'
    ]
    rc = triage_mod.main(argv)
    assert rc == 0

    # Assert files
    assert (out_dir / 'validation.json').exists()
    assert (out_dir / 'snow_draft.json').exists()
    assert (out_dir / 'snow_draft.md').exists()
    assert (out_dir / 'context' / 'prior_incidents.json').exists()
    assert (out_dir / 'context' / 'config.txt').exists()
    alarm_id = json.loads(Path('demo/alarms/A001.json').read_text())['alarm_id']
    assert (out_dir / f'{alarm_id}_pack.zip').exists()

    validation = json.loads((out_dir / 'validation.json').read_text())
    assert len(validation) == 3
    statuses = {r['ip']: r['status'] for r in validation}
    assert statuses['10.1.1.1'] == 'FAIL'
    assert statuses['10.1.2.11'] == 'PASS'
    assert statuses['10.1.2.12'] == 'PASS'

    snow = json.loads((out_dir / 'snow_draft.json').read_text())
    for key in ['short_description', 'description', 'site', 'device', 'ip', 'attachments']:
        assert key in snow
