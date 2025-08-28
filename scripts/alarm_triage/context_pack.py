"""Context pack assembly for an alarm triage run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any


def build_context(alarm: Dict[str, Any], repo_root: Path, ctx_dir: Path) -> Dict[str, Any]:
    ctx_dir.mkdir(parents=True, exist_ok=True)
    demo_dir = repo_root / "demo"

    # Prior incidents
    incidents_file = demo_dir / "incidents.json"
    incidents = []
    if incidents_file.is_file():
        try:
            all_incidents = json.loads(incidents_file.read_text(encoding="utf-8"))
            device = alarm.get("device")
            site = alarm.get("site")
            for inc in all_incidents:
                if device and inc.get("device") == device:
                    incidents.append(inc)
                elif site and inc.get("site") == site:
                    incidents.append(inc)
        except json.JSONDecodeError:
            pass
    (ctx_dir / "prior_incidents.json").write_text(
        json.dumps(incidents, indent=2), encoding="utf-8"
    )

    # Config (static demo config)
    config_src = demo_dir / "configs" / "rtr-site001-core.txt"
    config_text = config_src.read_text(encoding="utf-8") if config_src.is_file() else "demo config missing"
    (ctx_dir / "config.txt").write_text(config_text, encoding="utf-8")

    # Site diagram / notes
    site_file = demo_dir / "diagrams" / "site001.txt"
    if site_file.is_file():
        (ctx_dir / "site001.txt").write_text(site_file.read_text(encoding="utf-8"), encoding="utf-8")

    return {
        "incidents_count": len(incidents),
        "has_config": bool(config_text),
    }
