#!/usr/bin/env python3
"""Injection-rate sweep for the CHI traffic model, aggregated per subnet/channel.

For each total transaction rate (CHI_LAMBDA) it:
  1. regenerates chi_traffic via gen_chi_traffic.py (env CHI_LAMBDA),
  2. runs ../src/booksim chi_traffic,
  3. parses per-class stats from the final "Overall Traffic Statistics" block,
  4. aggregates classes into the four CHI channels (REQ/RSP/SNP/DAT) using the
     class_subnet vector from the generated config.

Output: ../doc/v5_chi_subnet_sweep.csv  (one row per (lambda, channel)).

BookSim aborts a run once average latency exceeds latency_thres (default 500
cycles) or the network goes unstable, so saturated points terminate quickly.
"""
import csv
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOOKSIM = os.path.join(ROOT, "src", "booksim")
GEN = os.path.join(HERE, "gen_chi_traffic.py")
CFG = os.path.join(HERE, "chi_traffic")
DOC = os.path.join(ROOT, "doc")
CSV_OUT = os.path.join(DOC, "v5_chi_subnet_sweep.csv")

CHANNELS = ["REQ", "RSP", "SNP", "DAT"]
SUBNET_CHANNEL = {0: "REQ", 1: "RSP", 2: "SNP", 3: "DAT"}

DEFAULT_LAMBDAS = [
    0.001, 0.002, 0.004, 0.006, 0.008, 0.010,
    0.014, 0.018, 0.024, 0.030, 0.038, 0.048,
    0.060, 0.075, 0.090, 0.110,
]


def lambdas():
    env = os.environ.get("SWEEP_LAMBDAS")
    if env:
        return [float(x) for x in env.replace(",", " ").split()]
    return DEFAULT_LAMBDAS


def regen(lam):
    env = dict(os.environ, CHI_LAMBDA=repr(lam))
    subprocess.run(["python3", GEN], env=env, cwd=HERE,
                   capture_output=True, check=True)


def read_vec(cfg_text, key):
    m = re.search(re.escape(key) + r"\s*=\s*\{([^}]*)\}", cfg_text)
    if not m:
        raise RuntimeError(f"{key} not found in config")
    return [int(x) for x in m.group(1).split(",")]


def class_meta():
    with open(CFG) as f:
        txt = f.read()
    subnet = read_vec(txt, "class_subnet")
    size = read_vec(txt, "packet_size")
    return subnet, size


def run_booksim():
    p = subprocess.run([BOOKSIM, "chi_traffic"], cwd=HERE,
                       capture_output=True, text=True, timeout=600)
    return p.stdout + p.stderr


def parse_overall(log):
    if "Overall Traffic Statistics" not in log:
        return None
    tail = log.split("Overall Traffic Statistics")[-1]
    out = {}
    block_re = re.compile(
        r"====== Traffic class (\d+) ======(.*?)"
        r"(?======= Traffic class|Total run time|$)", re.S)
    fields = {
        "plat": r"Packet latency average = ([0-9.eE+-]+|nan)",
        "flat": r"Flit latency average = ([0-9.eE+-]+|nan)",
        "inj_pkt": r"Injected packet rate average = ([0-9.eE+-]+)",
        "acc_pkt": r"Accepted packet rate average = ([0-9.eE+-]+)",
        "inj_flit": r"Injected flit rate average = ([0-9.eE+-]+)",
        "acc_flit": r"Accepted flit rate average = ([0-9.eE+-]+)",
        "hops": r"Hops average = ([0-9.eE+-]+|nan)",
    }
    for m in block_re.finditer(tail):
        c = int(m.group(1))
        body = m.group(2)
        row = {}
        for key, pat in fields.items():
            mm = re.search(pat, body)
            if not mm or mm.group(1).lower() == "nan":
                row[key] = None
            else:
                row[key] = float(mm.group(1))
        out[c] = row
    return out


def wavg(rows, val_key, w_key):
    num = den = 0.0
    for r in rows:
        v, w = r.get(val_key), r.get(w_key)
        if v is None or w is None or w <= 0:
            continue
        num += v * w
        den += w
    return num / den if den > 0 else None


def aggregate(subnet, size, stats):
    per_class = []
    for c, sub in enumerate(subnet):
        row = dict(stats.get(c, {}))
        row["channel"] = SUBNET_CHANNEL[sub]
        per_class.append(row)
    agg = {}
    for ch in CHANNELS:
        rows = [r for r in per_class if r["channel"] == ch]
        inj = sum((r.get("inj_flit") or 0.0) for r in rows)
        acc = sum((r.get("acc_flit") or 0.0) for r in rows)
        agg[ch] = {
            "inj_flit": inj,
            "acc_flit": acc,
            "inj_pkt": sum((r.get("inj_pkt") or 0.0) for r in rows),
            "acc_pkt": sum((r.get("acc_pkt") or 0.0) for r in rows),
            "accept_ratio": (acc / inj) if inj > 0 else None,
            "plat": wavg(rows, "plat", "acc_pkt"),
            "flat": wavg(rows, "flat", "acc_flit"),
            "hops": wavg(rows, "hops", "acc_flit"),
        }
    return agg


def main():
    rows = []
    sat_streak = 0
    print(f"{'lambda':>8} {'state':>6} | " +
          " | ".join(f"{ch:>3} lat/acc" for ch in CHANNELS))
    for lam in lambdas():
        regen(lam)
        subnet, size = class_meta()
        try:
            log = run_booksim()
        except subprocess.TimeoutExpired:
            print(f"{lam:>8} {'TIMO':>6} | (timeout)")
            sat_streak += 1
            if sat_streak >= 2:
                break
            continue
        saturated = ("Simulation unstable" in log) or ("Aborting simulation" in log)
        stats = parse_overall(log)
        if stats is None:
            print(f"{lam:>8} {'NODATA':>6} |")
            sat_streak += 1
            if sat_streak >= 2:
                break
            continue
        agg = aggregate(subnet, size, stats)
        state = "SAT" if saturated else "ok"
        cells = []
        for ch in CHANNELS:
            a = agg[ch]
            lat = a["flat"]
            acc = a["acc_flit"]
            cells.append(f"{(lat if lat is not None else 0):6.1f}/{acc:.4f}")
        print(f"{lam:>8} {state:>6} | " + " | ".join(cells))
        for ch in CHANNELS:
            a = agg[ch]
            rows.append([
                lam, ch, state,
                a["inj_flit"], a["acc_flit"], a["inj_pkt"], a["acc_pkt"],
                a["accept_ratio"], a["plat"], a["flat"], a["hops"],
            ])
        if saturated:
            sat_streak += 1
            if sat_streak >= 2:
                print("  -> two saturated points collected, stopping sweep")
                break
        else:
            sat_streak = 0

    os.makedirs(DOC, exist_ok=True)
    with open(CSV_OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lambda", "channel", "state", "inj_flit", "acc_flit",
                    "inj_pkt", "acc_pkt", "accept_ratio", "packet_latency",
                    "flit_latency", "hops"])
        w.writerows(rows)
    print(f"\nWrote {CSV_OUT} ({len(rows)} rows)")
    # restore baseline config so the repo's chi_traffic matches the single-point report
    regen(float(os.environ.get("CHI_BASE_LAMBDA", 0.001)))
    print("Restored baseline chi_traffic (CHI_LAMBDA=0.001)")


if __name__ == "__main__":
    main()
