"""Batch triage CLI for alarm files with KPI reporting.

Usage:
  python -m scripts.alarm_triage.batch --alarms "demo/alarms/*.json" --out outputs/batch --offline
"""
import argparse
import glob
import json
import time
from pathlib import Path
from statistics import median, quantiles
from scripts.alarm_triage import triage

def run_batch(alarms, out_dir, offline):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for alarm_path in alarms:
        try:
            data = json.loads(Path(alarm_path).read_text())
            if 'alarm_id' not in data:  # skip non-alarm JSON (e.g., probes_offline)
                continue
        except Exception:
            continue
        alarm_id = Path(alarm_path).stem
        alarm_out = out_dir / alarm_id
        timings = {}
        artifacts = {}
        rc = None
        t0 = time.monotonic()
        # Whole triage timing only (internals timed inside triage if needed)
        t_validate = time.monotonic()
        try:
            rc = triage.main([
                "--alarm", alarm_path,
                "--out", str(alarm_out),
                "--offline" if offline else ""
            ])
        except Exception as e:
            rc = -1
        t1 = time.monotonic()
        timings["validate_s"] = t1 - t_validate
        timings["total_s"] = t1 - t0
        # Check artifacts
        for fname in ["validation.json", "snow_draft.json", "snow_draft.md", "context/prior_incidents.json", "context/config.txt", f"{alarm_id}_pack.zip"]:
            p = alarm_out / fname if not fname.startswith("context/") else alarm_out / "context" / fname.split("/",1)[1]
            artifacts[fname] = p.exists()
        results.append({
            "alarm_id": alarm_id,
            "rc": rc,
            **timings,
            "artifacts": artifacts,
            "success": rc == 0 and all(artifacts.values())
        })
    # KPIs
    total_times = [r["total_s"] for r in results]
    p50 = median(total_times) if total_times else 0
    p95 = quantiles(total_times, n=100)[94] if len(total_times) >= 20 else max(total_times) if total_times else 0
    success_rate = sum(r["success"] for r in results) / len(results) if results else 0
    # Write batch_report.json
    (out_dir / "batch_report.json").write_text(json.dumps(results, indent=2))
    # Write kpi.csv
    with (out_dir / "kpi.csv").open("w") as f:
        f.write("alarm_id,total_s,validate_s,success\n")
        for r in results:
            f.write(f"{r['alarm_id']},{r['total_s']:.3f},{r['validate_s']:.3f},{int(r['success'])}\n")
    # Write kpi.md
    with (out_dir / "kpi.md").open("w") as f:
        f.write(f"# Batch KPI Report\n\n")
        f.write(f"**Alarms processed:** {len(results)}\n\n")
        f.write(f"**Success rate:** {success_rate:.2%}\n\n")
        f.write(f"**p50 total time:** {p50:.3f}s\n\n")
        f.write(f"**p95 total time:** {p95:.3f}s\n\n")
        f.write("| alarm_id | total_s | validate_s | success |\n|---|---|---|---|\n")
        for r in results:
            f.write(f"| {r['alarm_id']} | {r['total_s']:.3f} | {r['validate_s']:.3f} | {int(r['success'])} |\n")
    return results

def main():
    parser = argparse.ArgumentParser(description="Batch Alarm Triage")
    parser.add_argument("--alarms", required=True, help="Glob pattern or space-separated alarm JSONs")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--offline", action="store_true", help="Offline mode")
    args = parser.parse_args()
    # Expand alarms
    if "*" in args.alarms:
        alarms = sorted(glob.glob(args.alarms))
    else:
        alarms = args.alarms.split()
    run_batch(alarms, args.out, args.offline)

if __name__ == "__main__":
    main()
