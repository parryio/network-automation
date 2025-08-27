"""Context pack assembly for an alarm triage run.

Copies diagram, prior incidents, and config snippet into a context/ folder.
Optionally overlays a red circle on a PNG diagram using coordinates if Pillow
is available.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict

try:  # Optional dependency
    from PIL import Image, ImageDraw  # type: ignore
    PIL_AVAILABLE = True
except Exception:  # pragma: no cover - executed only when Pillow missing
    PIL_AVAILABLE = False


def build(site: str, device: str, files_root: Path, out_dir: Path) -> Dict:
    context_dir = out_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    meta: Dict[str, str] = {}

    diagrams_dir = files_root / "diagrams"
    incidents_file = files_root / "incidents.json"
    configs_dir = files_root / "configs"

    # Diagram selection priority: png, svg, txt
    diagram_base = diagrams_dir / site
    selected = None
    for ext in (".png", ".svg", ".txt"):
        candidate = diagram_base.with_suffix(ext)
        if candidate.exists():
            shutil.copy2(candidate, context_dir / candidate.name)
            selected = candidate.name
            meta["diagram"] = candidate.name
            break

    # Optional overlay if png and coords json
    coords_file = diagram_base.with_suffix('.coords.json')
    if selected and selected.endswith('.png') and coords_file.exists() and PIL_AVAILABLE:
        try:
            coords = json.loads(coords_file.read_text())
            img_path = context_dir / selected
            img = Image.open(img_path)
            draw = ImageDraw.Draw(img)
            x, y, r = coords.get('x', 0), coords.get('y', 0), coords.get('r', 20)
            draw.ellipse([(x - r, y - r), (x + r, y + r)], outline='red', width=4)
            overlay_name = 'diagram_overlay.png'
            img.save(context_dir / overlay_name)
            meta['diagram_overlay'] = overlay_name
        except Exception:
            pass  # Silent skip

    # Prior incidents
    if incidents_file.exists():
        try:
            incidents = json.loads(incidents_file.read_text()).get(site, [])
            (context_dir / 'prior_incidents.json').write_text(json.dumps(incidents, indent=2))
            meta['prior_incidents'] = 'prior_incidents.json'
        except Exception:
            pass

    # Config snippet
    config_file = configs_dir / f"{device}.txt"
    if config_file.exists():
        shutil.copy2(config_file, context_dir / 'config.txt')
        meta['config'] = 'config.txt'

    return meta

__all__ = ["build"]
