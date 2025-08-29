import json
from pathlib import Path
import types

# We import the UI app module but override filesystem interactions where needed.

import pytest
pytest.importorskip("streamlit")
from ui import app as ui_app  # noqa: F401


def test_row_source_excludes_meta(tmp_path, monkeypatch):
    # Create fake outputs structure
    out = tmp_path / 'outputs'
    out.mkdir()
    # Valid alarm dirs
    (out / 'A001').mkdir()
    (out / 'A001' / 'validation.json').write_text(json.dumps({'status': 'ok', 'ping_loss': 0}), encoding='utf-8')
    (out / 'A002').mkdir()
    (out / 'A002' / 'validation.json').write_text(json.dumps({'status': 'fail', 'ping_loss': 1}), encoding='utf-8')
    # Meta dir we must ignore
    (out / 'batch').mkdir()
    (out / 'batch' / 'validation.json').write_text(json.dumps({'status': 'ok'}), encoding='utf-8')

    # Alarm JSON files
    alarm_dir = tmp_path / 'demo' / 'alarms'
    alarm_dir.mkdir(parents=True)
    (alarm_dir / 'A001.json').write_text(json.dumps({'id': 'A001', 'severity': 'major'}), encoding='utf-8')
    (alarm_dir / 'A002.json').write_text(json.dumps({'id': 'A002', 'severity': 'minor'}), encoding='utf-8')

    # Use helpers from app
    from ui.app import resolve_alarm_paths, final_alarm_ids, EXCLUDE_META

    glob_pattern = str(alarm_dir / '*.json')
    alarm_paths = resolve_alarm_paths(glob_pattern)
    ids = [p.stem for p in alarm_paths]
    assert ids == ['A001', 'A002']

    ids_with_diag = final_alarm_ids(glob_pattern, out, include_diagnostics=False)
    assert ids_with_diag == ['A001', 'A002']

    # Ensure meta still excluded even if diagnostics toggle
    ids_with_diag2 = final_alarm_ids(glob_pattern, out, include_diagnostics=True)
    assert ids_with_diag2 == ['A001', 'A002']  # probes_offline not present so unchanged

    assert 'batch' in EXCLUDE_META
