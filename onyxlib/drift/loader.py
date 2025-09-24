"""Helpers for loading inventory and configuration data for drift detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml


@dataclass
class DeviceRecord:
    """Represents a device entry from the inventory file."""

    name: str
    platform: str
    running_config: str
    baseline_config: Optional[str]
    running_path: Path
    baseline_path: Optional[Path]


def load_inventory(path: Path) -> List[Dict[str, object]]:
    """Load a YAML inventory file."""

    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict) or "devices" not in data:
        raise ValueError("Inventory must be a mapping with a 'devices' key")
    devices = data["devices"]
    if not isinstance(devices, list):
        raise ValueError("Inventory 'devices' must be a list")
    return devices


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Expected configuration file at {path}")
    return path.read_text().strip()


def _candidate_paths(root: Path, name: str, preferred: Optional[str]) -> Iterable[Path]:
    if preferred:
        yield (root / preferred)
    patterns = [
        f"{name}.cfg",
        f"{name}.conf",
        f"{name}.txt",
        f"{name}.running",
        f"{name}.running.cfg",
    ]
    for pattern in patterns:
        yield root / pattern


def _candidate_baselines(root: Path, name: str, preferred: Optional[str]) -> Iterable[Path]:
    if preferred:
        yield root / preferred
    subdirs = [root / "baseline", root / "baselines", root / "golden"]
    for subdir in subdirs:
        if preferred:
            yield subdir / preferred
        for suffix in (".cfg", ".conf", ".txt", ".golden.cfg", ".baseline", ".baseline.cfg"):
            yield subdir / f"{name}{suffix}"
    for suffix in (".baseline", ".baseline.cfg", ".golden", ".golden.cfg"):
        yield root / f"{name}{suffix}"


def _first_existing(paths: Iterable[Path]) -> Optional[Path]:
    for candidate in paths:
        if candidate.exists():
            return candidate
    return None


def load_device_configs(inventory: List[Dict[str, object]], configs_dir: Path) -> List[DeviceRecord]:
    """Resolve configuration paths for each device in the inventory."""

    records: List[DeviceRecord] = []
    configs_root = Path(configs_dir)

    for entry in inventory:
        if not isinstance(entry, dict):
            raise ValueError("Inventory entries must be mappings")
        name = str(entry.get("name"))
        platform = str(entry.get("platform", "unknown"))
        running_hint = entry.get("running") or entry.get("running_config") or entry.get("config")
        baseline_hint = entry.get("baseline") or entry.get("baseline_config")

        running_path = _first_existing(_candidate_paths(configs_root, name, running_hint if isinstance(running_hint, str) else None))
        if running_path is None:
            raise FileNotFoundError(f"Unable to locate running config for {name}")

        baseline_path = _first_existing(_candidate_baselines(configs_root, name, baseline_hint if isinstance(baseline_hint, str) else None))

        running_config = _read_text(running_path)
        baseline_config = _read_text(baseline_path) if baseline_path else None

        records.append(
            DeviceRecord(
                name=name,
                platform=platform,
                running_config=running_config,
                baseline_config=baseline_config,
                running_path=running_path,
                baseline_path=baseline_path,
            )
        )

    return records
