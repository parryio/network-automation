from __future__ import annotations
import os
import time
import yaml
import shutil
from pathlib import Path
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_fixed
from netmiko import ConnectHandler

CONFIG_LATEST = "configs/latest"

class Device(BaseModel):
    name: str
    ip: str
    platform: str = Field(..., description="netmiko device_type, e.g., cisco_ios")
    username: str
    port: int = 22
    secret: str = ""

    def netmiko_dict(self, password: str) -> Dict[str, Any]:
        return {
            "device_type": self.platform,
            "host": self.ip,
            "username": self.username,
            "password": password,
            "port": self.port,
            "secret": self.secret or None,
            "fast_cli": True,
            "conn_timeout": 10,
            "banner_timeout": 20,
        }

def load_devices(inventory_path: str | Path) -> List[Device]:
    data = yaml.safe_load(Path(inventory_path).read_text())
    return [Device(**item) for item in data]

def get_password() -> str:
    pw = os.getenv("NET_PASS")
    if not pw:
        raise RuntimeError("NET_PASS environment variable is not set. Export your device password.")
    return pw

def ensure_dir(p: str | Path) -> Path:
    p = Path(p)
    p.mkdir(parents=True, exist_ok=True)
    return p

def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)

def make_stamp_dir(root: str | Path) -> Path:
    root = ensure_dir(root)
    stamp = time.strftime("%Y-%m-%d")
    day = root / stamp
    ensure_dir(day)
    # refresh configs/latest (Windows-safe copy instead of symlink)
    latest = Path(CONFIG_LATEST)
    if latest.exists():
        if latest.is_symlink():
            latest.unlink(missing_ok=True)
        else:
            shutil.rmtree(latest, ignore_errors=True)
    shutil.copytree(day, latest)
    return day

@retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
def connect(device: Device, password: str) -> ConnectHandler:
    return ConnectHandler(**device.netmiko_dict(password))

def enable_if_needed(conn: ConnectHandler, device: Device) -> None:
    if device.secret:
        try:
            conn.enable()
        except Exception:
            pass

def ios_run_cmd(conn: ConnectHandler, cmd: str) -> str:
    return conn.send_command(cmd, use_textfsm=False)

def ios_config_set(conn: ConnectHandler, lines: List[str]) -> str:
    return conn.send_config_set(lines)

def save_ios(conn: ConnectHandler) -> None:
    try:
        conn.save_config()
    except Exception:
        conn.send_command_timing("write memory")
