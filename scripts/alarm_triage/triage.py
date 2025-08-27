"""Alarm triage CLI entrypoint.

Example:
    python -m scripts.alarm_triage.triage --alarm demo/alarms/A001.json --out outputs/A001 --offline
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
import zipfile
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict
import yaml

from . import probes, context_pack, snow_payload
from .insights import compute_insights

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = REPO_ROOT / 'demo'


def _audit(log_file: Path, event: str, meta: Dict):
    log_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now(UTC).isoformat(), "event": event, **meta}
    with log_file.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')


def load_alarm(path: Path) -> Dict:
    return json.loads(path.read_text())


def load_inventory(path: Path) -> Dict:
    return yaml.safe_load(path.read_text())


def derive_neighbors(alarm: Dict, inventory: Dict) -> Dict[str, str]:
    site = alarm.get('site')
    site_data = (inventory.get('sites') or {}).get(site, {})
    neighbors = {}
    for item in site_data.get('neighbors', []) or []:
        # each neighbor: label: ip
        if isinstance(item, str) and ':' in item:
            # not expected by spec, but graceful
            label, ip = item.split(':', 1)
            neighbors[label.strip()] = ip.strip()
        elif isinstance(item, str):
            # sw-site001-edge01: 10.1.2.11 pattern? Provided in YAML list as "name: ip"
            parts = item.split()
        elif isinstance(item, dict):
            for k,v in item.items():
                neighbors[k] = str(v)
        else:
            pass
    # Provided spec uses list of 'label: ip' style entries (YAML list of mappings). We will also handle mapping style:
    if isinstance(site_data.get('neighbors'), list):
        for mapping in site_data.get('neighbors'):
            if isinstance(mapping, dict):
                for k,v in mapping.items():
                    neighbors[k] = str(v)
            elif isinstance(mapping, str) and ':' in mapping:
                k,v = mapping.split(':',1)
                neighbors[k.strip()] = v.strip()
    return neighbors


def main(argv=None):
    parser = argparse.ArgumentParser(description='Alarm Triage (read-only)')
    parser.add_argument('--alarm', required=True, help='Path to alarm JSON')
    parser.add_argument('--out', required=True, help='Output directory')
    parser.add_argument('--offline', action='store_true', help='Use canned probe results (deterministic)')
    parser.add_argument('--with-traceroute', action='store_true', help='Include traceroute (skipped by default)')
    args = parser.parse_args(argv)

    alarm_path = Path(args.alarm).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_file = out_dir / 'audit.jsonl'

    _audit(audit_file, 'start', {'alarm': str(alarm_path)})

    alarm = load_alarm(alarm_path)
    inventory = load_inventory(DEMO_ROOT / 'inventory.yml')
    neighbors = derive_neighbors(alarm, inventory)

    _audit(audit_file, 'loaded', {'neighbors': neighbors})

    validation = probes.validate(alarm.get('ip'), neighbors, offline=args.offline, with_traceroute=args.with_traceroute)
    (out_dir / 'validation.json').write_text(json.dumps(validation, indent=2))
    _audit(audit_file, 'validated', {'count': len(validation)})

    context_meta = context_pack.build(alarm.get('site'), alarm.get('device'), DEMO_ROOT, out_dir)
    _audit(audit_file, 'context_built', context_meta)

    # Compute insights (blast radius / next steps)
    site = alarm.get('site')
    site_data = (inventory.get('sites') or {}).get(site, {})
    insights = compute_insights(alarm, validation, site_data)
    payload, markdown = snow_payload.build(alarm, validation, context_meta, insights=insights)
    (out_dir / 'snow_draft.json').write_text(json.dumps(payload, indent=2))
    (out_dir / 'snow_draft.md').write_text(markdown)
    _audit(audit_file, 'snow_draft', {'attachments': payload.get('attachments')})

    # Zip artifact
    zip_name = f"{alarm.get('alarm_id')}_pack.zip"
    zip_path = out_dir / zip_name
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for p in out_dir.rglob('*'):
            if p.is_file() and p != zip_path:
                zf.write(p, arcname=p.relative_to(out_dir))
    _audit(audit_file, 'packaged', {'zip': zip_name})

    _audit(audit_file, 'done', {})
    return 0

if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
