#!/usr/bin/env python3
"""Injection-rate sweep for the 4-channel CHI mesh model.

For each offered load (per-node, per-class REQ injection rate) it regenerates
mesh6x7_chi via gen_chi_mesh.py (env override CHI_INJ) and runs BookSim, then
parses the Overall + per-class accepted flit rate and average packet latency.
Stops the curve at the first saturation point (run aborts / latency explodes).

Writes results to chi_sweep_results.csv and prints a table.
"""
import os, re, subprocess, csv

here = os.path.dirname(os.path.abspath(__file__))
BOOKSIM = os.path.join(here, "..", "src", "booksim")
SNOOP = os.environ.get("CHI_SNOOP", "1.0")
LOADS = [0.004, 0.006, 0.008, 0.010, 0.011, 0.012, 0.013, 0.014, 0.015, 0.016, 0.018, 0.020]

def run(inj):
    env = dict(os.environ, CHI_INJ=str(inj), CHI_SNOOP=SNOOP)
    subprocess.run(["python3", os.path.join(here, "gen_chi_mesh.py")],
                   env=env, cwd=here, capture_output=True, check=True)
    p = subprocess.run([BOOKSIM, "mesh6x7_chi"], cwd=here,
                       capture_output=True, text=True)
    return p.stdout + p.stderr

def grab_overall(log):
    # Overall (drained) averages, present only if the run converged
    lat = re.search(r"Packet latency average = ([\d.]+) \(.*?total\)", log)
    acc = re.search(r"Accepted flit rate average = ([\d.]+) \(.*?total\)", log)
    return (float(lat.group(1)) if lat else None,
            float(acc.group(1)) if acc else None)

def grab_class(log, cls):
    m = re.search(rf"====== Traffic class {cls} ======(.*?)(?:======|Total run time)",
                  log, re.S)
    if not m:
        return None, None
    blk = m.group(1)
    lat = re.search(r"Packet latency average = ([\d.]+)", blk)
    acc = re.search(r"Accepted flit rate average = ([\d.]+)", blk)
    return (float(lat.group(1)) if lat else None,
            float(acc.group(1)) if acc else None)

rows = []
print(f"snoop_factor={SNOOP}")
print(f"{'offered':>8} {'state':>10} {'lat_all':>8} {'acc_all':>8} "
      f"{'lat_c0':>8} {'acc_c0':>8} {'lat_c1':>8} {'acc_c1':>8}")
for inj in LOADS:
    log = run(inj)
    saturated = "exceeded" in log or "Simulation unstable" in log
    lat_a, acc_a = grab_overall(log)
    lat0, acc0 = grab_class(log, 0)
    lat1, acc1 = grab_class(log, 1)
    state = "SAT" if saturated else "ok"
    def f(x): return f"{x:.4f}" if isinstance(x, float) else "-"
    print(f"{inj:>8} {state:>10} {f(lat_a):>8} {f(acc_a):>8} "
          f"{f(lat0):>8} {f(acc0):>8} {f(lat1):>8} {f(acc1):>8}")
    rows.append([inj, state, lat_a, acc_a, lat0, acc0, lat1, acc1])
    if saturated:
        print("  -> saturation reached, stopping sweep")
        break

out = os.path.join(here, "chi_sweep_results.csv")
with open(out, "w", newline="") as fcsv:
    w = csv.writer(fcsv)
    w.writerow(["offered_inj", "state", "lat_all", "acc_all",
                "lat_c0", "acc_c0", "lat_c1", "acc_c1"])
    w.writerows(rows)
print(f"\nWrote {out}")
