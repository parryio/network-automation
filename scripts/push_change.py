from __future__ import annotations
import re
from pathlib import Path
from typing import List
import difflib
import typer
from rich import print
from rich.table import Table
from scripts.utils import (
    load_devices, get_password, connect, enable_if_needed,
    ios_run_cmd, ios_config_set, atomic_write, ensure_dir, save_ios
)

app = typer.Typer(help="Push standard changes with dry-run and diffs. Supports offline demo mode.")

def parse_ntp(cfg: str) -> set[str]:
    return {m.group(1) for m in re.finditer(r"^ntp\\s+server\\s+(\\S+)", cfg, flags=re.MULTILINE)}

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
    banner = banner.replace("\\r", "")
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

# ---------- Offline text transforms (idempotent) ----------
def apply_ntp_to_config(text: str, desired: List[str], enforce: bool) -> str:
    lines = text.splitlines()
    if enforce:
        lines = [ln for ln in lines if not re.match(r"^ntp\\s+server\\s+\\S+\\s*$", ln)]
        current: set[str] = set()
    else:
        current = parse_ntp("\n".join(lines))
    for s in desired:
        if s and (s not in current):
            lines.append(f"ntp server {s}")
    out = "\n".join(lines)
    return out if out.endswith("\n") else out + "\n"

def apply_banner_to_config(text: str, banner: str | None) -> str:
    if not banner:
        return text
    cleaned = re.sub(r"^banner login \\^C.*?\\^C\\s*$", "", text, flags=re.MULTILINE | re.DOTALL).rstrip("\n")
    if cleaned and not cleaned.endswith("\n\n"):
        cleaned += "\n\n"
    elif not cleaned:
        cleaned = ""
    cleaned += f"banner login ^C{banner.strip()}^C\n"
    return cleaned if cleaned.endswith("\n") else cleaned + "\n"

def apply_disable_http(text: str, disable: bool) -> str:
    if not disable:
        return text
    # Remove ALL enabled http server lines (handles leading spaces and any suffix)
    t = re.sub(r'^\s*ip http server(?:\b.*)?\s*$', '', text, flags=re.MULTILINE)
    # Collapse excessive blank lines introduced
    t = re.sub(r'\n{3,}', '\n\n', t)
    # Ensure explicit disable line exists once
    if re.search(r'^\s*no ip http server\b', t, flags=re.MULTILINE) is None:
        t = (t.rstrip('\n') + '\nno ip http server\n')
    return t if t.endswith('\n') else t + '\n'

def apply_ssh_v2(text: str, enable: bool) -> str:
    if not enable:
        return text
    if "ip ssh version 2" not in text:
        text = (text.rstrip("\n") + "\nip ssh version 2\n")
    return text if text.endswith("\n") else text + "\n"

def apply_transport_ssh(text: str, enable: bool) -> str:
    if not enable:
        return text
    # Replace telnet with ssh if present; otherwise ensure one 'transport input ssh' exists
    t = re.sub(r"^\\s*transport input\\s+telnet\\s*$", " transport input ssh", text, flags=re.MULTILINE)
    if "transport input ssh" not in t:
        t = (t.rstrip("\n") + "\ntransport input ssh\n")
    return t if t.endswith("\n") else t + "\n"

def apply_timestamps(text: str, enable: bool) -> str:
    if not enable:
        return text
    if "service timestamps log datetime msec" not in text:
        text = (text.rstrip("\n") + "\nservice timestamps log datetime msec\n")
    return text if text.endswith("\n") else text + "\n"
# ----------------------------------------------------------

@app.command()
def main(
    inventory: Path = typer.Option("devices.yaml", "--inventory", "-i"),
    ntp: str = typer.Option("", "--ntp", help="Comma-separated NTP servers (e.g. '1.1.1.1,1.0.0.1')"),
    banner: str = typer.Option("", "--banner", help="Login banner text"),
    enforce: bool = typer.Option(False, "--enforce", help="Remove extra NTP servers not in desired set"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan, do not apply"),
    diffs: Path = typer.Option(Path("diffs"), "--diffs", help="Folder to write unified diffs"),
    # offline demo mode
    offline: bool = typer.Option(False, "--offline", help="Offline demo mode (no SSH)"),
    before: Path = typer.Option(None, "--before", help="Path to a .cfg to treat as 'before' (offline only)"),
    name: str = typer.Option("offline-device", "--name", help="Device name for diff filename (offline only)"),
    write_after: bool = typer.Option(False, "--write-after", help="Write AFTER config (offline only)"),
    after_out: Path = typer.Option(Path("configs/after_demo"), "--after-out", help="Folder to write AFTER config (offline only)"),
    # optional baseline-fixers to make audit pass
    fix_ssh: bool = typer.Option(False, "--fix-ssh", help="Ensure 'ip ssh version 2' and 'transport input ssh'"),
    disable_http: bool = typer.Option(False, "--disable-http", help="Remove 'ip http server'"),
    timestamps: bool = typer.Option(False, "--timestamps", help="Ensure 'service timestamps log datetime msec'"),
):
    desired_ntp = [s.strip() for s in ntp.split(",") if s.strip()] if ntp else []
    diffs_dir = ensure_dir(diffs)

    table = Table(title="Change Plan")
    table.add_column("Device")
    table.add_column("To Apply")

    # -------- OFFLINE MODE --------
    if offline:
        if not before or not before.exists():
            raise typer.BadParameter("--before must point to a .cfg file in offline mode")
        before_text = before.read_text(encoding="utf-8", errors="ignore")

        # Build "cmds" for display only (what we'd do on a live device)
        cmds: List[str] = []
        if desired_ntp:
            current_ntp = parse_ntp(before_text)
            cmds += build_ntp_commands(current_ntp, desired_ntp, enforce)
        cmds += build_banner_commands(banner or None)
        if disable_http:
            cmds.append("no ip http server")
        if fix_ssh:
            cmds += ["ip ssh version 2", "line vty 0 4", " transport input ssh", "exit"]
        if timestamps:
            cmds.append("service timestamps log datetime msec")

        table.add_row(name, "\n".join(cmds) if cmds else "(no changes)")
        print(table)

        if dry_run or not cmds:
            print("[bold yellow]Dry-run only. No changes applied.[/bold yellow]" if dry_run else "[bold]No changes necessary.[/bold]")
            return

        # Apply transforms to produce AFTER text
        after_text = before_text
        if desired_ntp:
            after_text = apply_ntp_to_config(after_text, desired_ntp, enforce)
        if banner:
            after_text = apply_banner_to_config(after_text, banner)
        if disable_http:
            after_text = apply_disable_http(after_text, True)
        if fix_ssh:
            after_text = apply_ssh_v2(after_text, True)
            after_text = apply_transport_ssh(after_text, True)
        if timestamps:
            after_text = apply_timestamps(after_text, True)

        # Diff + optional write-after
        diff_text = unified_diff_text(before_text, after_text, name)
        atomic_write(diffs_dir / f"{name}.diff", diff_text)
        print(f"Diff written to: [bold]{diffs_dir / (name + '.diff')}[/bold]")

        if write_after:
            outdir = ensure_dir(after_out)
            atomic_write(outdir / f"{name}.cfg", after_text if after_text.endswith("\n") else (after_text + "\n"))
            print(f"After-config written to: [bold]{outdir / (name + '.cfg')}[/bold]")
        return

    # -------- LIVE MODE (unchanged behavior) --------
    devices = load_devices(inventory)
    password = get_password()

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
            if disable_http:
                cmds.append("no ip http server")
            if fix_ssh:
                cmds += ["ip ssh version 2", "line vty 0 4", " transport input ssh", "exit"]
            if timestamps:
                cmds.append("service timestamps log datetime msec")

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
