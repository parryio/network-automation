from __future__ import annotations
import re
from pathlib import Path
from typing import List
import difflib
import typer
from rich import print
from rich.table import Table
from scripts.utils import load_devices, get_password, connect, enable_if_needed, ios_run_cmd, ios_config_set, atomic_write, ensure_dir, save_ios

app = typer.Typer(help="Push standard changes with dry-run and diffs.")

def parse_ntp(cfg: str) -> set[str]:
    return {m.group(1) for m in re.finditer(r"^ntp\s+server\s+(\S+)", cfg, flags=re.MULTILINE)}

def build_ntp_commands(current: set[str], desired: List[str], enforce: bool) -> List[str]:
    desired_set = set(desired)
    cmds: List[str] = []
    for s in sorted(desired_set - current):
        cmds.append(f"ntp server {s}")
    if enforce:
        for s in sorted(current - desired_set):
            cmds.append(f"no ntp server {s}")
    return cmds

def build_banner_commands(banner: str | None) -> List[str]:
    if not banner:
        return []
    banner = banner.replace("\r", "")
    return ["banner login ^C" + banner + "^C"]

def unified_diff_text(before: str, after: str, name: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"before/{name}",
        tofile=f"after/{name}",
        n=3,
    )
    return "".join(diff)

@app.command()
def main(
    inventory: Path = typer.Option("devices.yaml", "--inventory", "-i"),
    ntp: str = typer.Option("", "--ntp", help="Comma-separated NTP servers (e.g. '1.1.1.1,1.0.0.1')"),
    banner: str = typer.Option("", "--banner", help="Login banner text"),
    enforce: bool = typer.Option(False, "--enforce", help="Remove extra NTP servers not in desired set"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan, do not apply"),
    diffs: Path = typer.Option(Path("diffs"), "--diffs", help="Folder to write unified diffs"),
):
    devices = load_devices(inventory)
    password = get_password()

    desired_ntp = [s.strip() for s in ntp.split(",") if s.strip()] if ntp else []
    diffs_dir = ensure_dir(diffs)

    table = Table(title="Change Plan")
    table.add_column("Device")
    table.add_column("To Apply")

    for d in devices:
        try:
            conn = connect(d, password)
            enable_if_needed(conn, d)
            before = ios_run_cmd(conn, "show running-config")
            cmds: List[str] = []
            if desired_ntp:
                current_ntp = parse_ntp(before)
                cmds += build_ntp_commands(current_ntp, desired_ntp, enforce)
            cmds += build_banner_commands(banner or None)

            table.add_row(d.name, "\n".join(cmds) if cmds else "(no changes)")

            if not dry_run and cmds:
                ios_config_set(conn, cmds)
                save_ios(conn)
                after = ios_run_cmd(conn, "show running-config")
                diff_text = unified_diff_text(before, after, d.name)
                atomic_write(diffs_dir / f"{d.name}.diff", diff_text)

            conn.disconnect()
        except Exception as e:
            table.add_row(d.name, f"ERROR: {e}")

    print(table)
    if dry_run:
        print("[bold yellow]Dry-run only. No changes applied.[/bold yellow]")
    else:
        print(f"Diffs (if any) written to: [bold]{diffs_dir}[/bold]")

if __name__ == "__main__":
    app()
