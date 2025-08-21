from __future__ import annotations
import shutil
import typer
from rich import print
from rich.table import Table
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple
from scripts.utils import load_devices, get_password, make_stamp_dir, ios_run_cmd, connect, enable_if_needed, atomic_write

app = typer.Typer(help="Backup running configs in parallel or from local demo files.")

DEFAULT_SHOW = {
    "cisco_ios": "show running-config",
}

def backup_one(out_dir: Path, device, password: str) -> Tuple[str, str, bool, str]:
    try:
        conn = connect(device, password)
        enable_if_needed(conn, device)
        cmd = DEFAULT_SHOW.get(device.platform, "show running-config")
        cfg = ios_run_cmd(conn, cmd)
        conn.disconnect()
        fname = f"{device.name}_{device.ip}_{device.platform}.cfg"
        atomic_write(out_dir / fname, cfg)
        return (device.name, device.ip, True, "OK")
    except Exception as e:
        return (device.name, device.ip, False, str(e))

@app.command()
def main(
    inventory: Path = typer.Option("devices.yaml", "--inventory", "-i", help="YAML inventory"),
    out: Path = typer.Option("configs", "--out", "-o", help="Output root folder"),
    workers: int = typer.Option(8, "--workers", "-w", help="Parallel workers"),
    offline_from: Path = typer.Option(None, "--offline-from", help="Copy .cfg files from this folder into today's backup (demo mode)"),
):
    day_dir = make_stamp_dir(out)

    # Offline demo: copy existing .cfg files into today's folder
    if offline_from:
        table = Table(title=f"Offline Backup (copy) → {day_dir}")
        table.add_column("Source")
        table.add_column("Dest")
        ok = 0
        for p in sorted(Path(offline_from).glob("*.cfg")):
            dest = day_dir / p.name
            shutil.copy2(p, dest)
            table.add_row(str(p), str(dest))
            ok += 1
        print(table)
        print(f"[bold]{ok} file(s) copied[/bold]")
        return

    # Live mode: connect to devices
    devices = load_devices(inventory)
    password = get_password()

    results: List[Tuple[str, str, bool, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(backup_one, day_dir, d, password) for d in devices]
        for fut in as_completed(futs):
            results.append(fut.result())

    table = Table(title=f"Backups → {day_dir}")
    table.add_column("Device")
    table.add_column("IP")
    table.add_column("Status")
    table.add_column("Note")
    ok = 0
    for name, ip, success, note in sorted(results):
        table.add_row(name, ip, "[green]OK" if success else "[red]FAIL", note)
        ok += 1 if success else 0
    print(table)
    print(f"[bold]{ok}/{len(results)} successful[/bold]")

if __name__ == "__main__":
    app()
