# Network Automation

Practical network automation scripts (Python/Netmiko) for three real tasks:

- **Backups** – parallel running-config backups to dated folders with a `latest` copy
- **Baseline audit** – lint saved configs against a minimal security/compliance baseline
- **Safe change push** – roll out standard changes (NTP + login banner) with `--dry-run` and unified diffs

## Quickstart (Windows PowerShell)

```powershell
# create venv and install deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# set password for your devices (never commit passwords)
$env:NET_PASS = "your_password_here"

# edit devices.yaml with real IPs and usernames before running
