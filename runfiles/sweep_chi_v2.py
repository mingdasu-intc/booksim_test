#!/usr/bin/env python3
"""Injection-rate sweep for the V2 (class_subnet) CHI mesh model.

For each base request rate it regenerates mesh6x7_chi_v2 (env CHI_INJ) and runs
BookSim, parsing per-class average packet latency + accepted flit rate. Stops at
the first saturation (run reports 'unstable'). Writes chi_v2_sweep_results.csv.
"""
import os, re, subprocess, csv

here = os.path.dirname(os.path.abspath(__file__))
BOOKSIM = os.path.join(here, "..", "src", "booksim")
SNOOP = os.environ.get("CHI_SNOOP", "1.0")
WFRAC = os.environ.get("CHI_WFRAC", "0.3")
LOADS = [0.0004, 0.0006, 0.0008, 0.0010, 0.0012, 0.0014, 0.0016, 0.0018, 0.0020]
NAMES = {0: "REQ", 1: "DAT_rd", 2: "SNP", 3: "RSP", 4: "DAT_wr"}

def run(inj):
    env = dict(os.environ, CHI_INJ=str(inj), CHI_SNOOP=SNOOP, CHI_WFRAC=WFRAC)
    subprocess.run(["python3", os.path.join(here, "gen_chi_mesh_v2.py")],
                   env=env, cwd=here, capture_output=True, check=True)
    p = subprocess.run([BOOKSIM, "mesh6x7_chi_v2"], cwd=here,
                       capture_output=True, text=True)
    return p.stdout + p.stderr

def parse(log):
    """Return {class: (lat, acc_flit)} from final Overall section."""
    if "Overall Traffic Statistics" not in log:
        return None
    tail = log.split("Overall Traffic Statistics")[-1]
    out = {}
    for m in re.finditer(r"====== Traffic class (\d+) ======(.*?)"
                         r"(?======= Traffic class|Total run time)", tail, re.S):
        c = int(m.group(1)); b = m.group(2)
        lat = re.search(r"Packet latency average = ([\d.]+)", b)
        acc = re.search(r"Accepted flit rate average = ([\d.]+)", b)
        out[c] = (float(lat.group(1)) if lat else None,
                  float(acc.group(1)) if acc else None)
    return out

rows = []
print(f"snoop_factor={SNOOP}  write_fraction={WFRAC}")
hdr = f"{'offered':>9} {'state':>9}" + "".join(f" {NAMES[c]+'_lat':>10}" for c in range(5))
print(hdr)
for inj in LOADS:
    log = run(inj)
    unstable = "unstable" in log or "exceeded" in log
    res = parse(log)
    state = "SAT" if (unstable or res is None) else "ok"
    cells = ""
    row = [inj, state]
    for c in range(5):
        if res and c in res and res[c][0] is not None:
            lat, acc = res[c]
            cells += f" {lat:>10.1f}"
            row += [lat, acc]
        else:
            cells += f" {'-':>10}"
            row += [None, None]
    print(f"{inj:>9} {state:>9}{cells}")
    rows.append(row)
    if state == "SAT":
        print("  -> saturation reached, stopping")
        break

out = os.path.join(here, "chi_v2_sweep_results.csv")
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    head = ["offered", "state"]
    for c in range(5):
        head += [f"{NAMES[c]}_lat", f"{NAMES[c]}_acc"]
    w.writerow(head)
    w.writerows(rows)
print(f"\nWrote {out}")
