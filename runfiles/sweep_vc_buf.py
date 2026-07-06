#!/usr/bin/env python3
"""vc_buf_size sensitivity sweep for the SN read/write throughput CEILING.

For each VC buffer depth, run the read-focused and write-focused lambda sweeps
(all traffic forced to the SNs) and record the per-SN data-throughput plateau
(the max sustained accepted rate across the offered-load sweep). This isolates
how much of the 1 flit/cycle SN terminal link the interconnect can actually use
as the buffer grows relative to the link credit round-trip.

Reuses the parsing/aggregation helpers from sweep_sn_throughput.py.

Output: ../doc/v6_repair_vc_buf_sweep.csv  (override via SWEEP_OUT)
Env:
  SWEEP_BUFS     space/comma list of vc_buf_size values (default "2 4 8 16 32")
  SWEEP_LAMBDAS  offered-load points (default covers read+write plateaus)
  SWEEP_OUT      output csv name in doc/
Baseline knobs (routing=xy, link_latency=2) are fixed; buffer is the variable.
"""
import csv
import os

import sweep_sn_throughput as S

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(os.path.dirname(HERE), "doc")
CSV_OUT = os.path.join(DOC, os.environ.get("SWEEP_OUT", "v6_repair_vc_buf_sweep.csv"))

DEFAULT_BUFS = [2, 4, 8, 16, 32]
DEFAULT_LAMBDAS = [0.02, 0.03, 0.05, 0.08, 0.12, 0.2, 0.3, 0.5, 0.8]

BASE = {"CHI_ROUTING": "xy", "CHI_LINK_LATENCY": "2"}
READ_MIX = {
    "CHI_READ_RATIO": "100", "CHI_WRITE_RATIO": "0",
    "CHI_DATALESS_RATIO": "0", "CHI_CMO_RATIO": "0",
    "CHI_READ_SHARED_RATIO": "100", "CHI_READ_UNIQUE_RATIO": "0",
    "CHI_READ_NOSNP_RATIO": "0", "CHI_READ_L3_HIT_RATIO": "0",
    "CHI_READ_DMT_MISS_RATIO": "100", "CHI_READ_DCT_RATIO": "0",
}
WRITE_MIX = {
    "CHI_WRITE_RATIO": "100", "CHI_READ_RATIO": "0",
    "CHI_DATALESS_RATIO": "0", "CHI_CMO_RATIO": "0",
    "CHI_WRITE_BACK_RATIO": "100", "CHI_WRITE_UNIQUE_RATIO": "0",
    "CHI_WRITE_CLEAN_RATIO": "0", "CHI_WRITE_EVICT_RATIO": "0",
    "CHI_L3_EVICT_TO_SN_RATE": "1.0",
}


def parse_list(env, default, cast):
    v = os.environ.get(env)
    if not v:
        return default
    return [cast(x) for x in v.replace(",", " ").split()]


def set_chi_env(d):
    for k in list(os.environ):
        if k.startswith("CHI_"):
            del os.environ[k]
    os.environ.update(d)


def read_nodes():
    with open(S.CFG) as f:
        txt = f.read()
    import re
    m = re.search(r"=\s*(\d+)\s*nodes", txt)
    return int(m.group(1)) if m else 172


def sweep_mix(kind, lambdas):
    """Return the plateau (max per-SN accepted) row for one focused mix."""
    best = None
    nodes = None
    for lam in lambdas:
        S.regen(lam)
        if nodes is None:
            nodes = read_nodes()
        read_cls, write_cls, nsn = S.class_meta()
        log = S.run_booksim()
        saturated = ("Simulation unstable" in log) or ("Aborting simulation" in log)
        stats = S.parse_overall(log)
        unstable = False
        if stats is None:
            stats = S.parse_last_display(log)
            unstable = True
        if stats is None:
            continue
        cls = read_cls if kind == "read" else write_cls
        g = S.group(stats, cls, nodes, nsn)
        state = "UNSTBL" if unstable else ("SAT" if saturated else "ok")
        if best is None or g["acc_per_sn"] > best["per_sn"]:
            best = {"per_sn": g["acc_per_sn"], "total": g["acc_total"],
                    "util": g["util"], "flat": g["flat"], "lambda": lam,
                    "state": state}
    return best


def main():
    bufs = parse_list("SWEEP_BUFS", DEFAULT_BUFS, int)
    lambdas = parse_list("SWEEP_LAMBDAS", DEFAULT_LAMBDAS, float)

    rows = []
    print(f"{'vc_buf':>6} | {'rd/SN':>8} {'rd util':>7} {'rd@lam':>7} {'st':>6} | "
          f"{'wr/SN':>8} {'wr util':>7} {'wr@lam':>7} {'st':>6}")
    for buf in bufs:
        set_chi_env({**BASE, **READ_MIX, "CHI_VC_BUF_SIZE": str(buf)})
        rd = sweep_mix("read", lambdas)
        set_chi_env({**BASE, **WRITE_MIX, "CHI_VC_BUF_SIZE": str(buf)})
        wr = sweep_mix("write", lambdas)
        rd = rd or {"per_sn": 0, "util": 0, "total": 0, "lambda": 0, "state": "-", "flat": None}
        wr = wr or {"per_sn": 0, "util": 0, "total": 0, "lambda": 0, "state": "-", "flat": None}
        print(f"{buf:>6} | {rd['per_sn']:8.4f} {rd['util']:6.1%} {rd['lambda']:7.3f} "
              f"{rd['state']:>6} | {wr['per_sn']:8.4f} {wr['util']:6.1%} "
              f"{wr['lambda']:7.3f} {wr['state']:>6}")
        rows.append([buf,
                     rd["per_sn"], rd["total"], rd["util"], rd["lambda"], rd["state"], rd["flat"],
                     wr["per_sn"], wr["total"], wr["util"], wr["lambda"], wr["state"], wr["flat"]])

    os.makedirs(DOC, exist_ok=True)
    with open(CSV_OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["vc_buf_size",
                    "read_per_sn", "read_total", "read_util", "read_lambda", "read_state", "read_flat",
                    "write_per_sn", "write_total", "write_util", "write_lambda", "write_state", "write_flat"])
        w.writerows(rows)
    print(f"\nWrote {CSV_OUT} ({len(rows)} rows)")

    # restore persisted baseline (default ratios, buf=2, xy, latency=2, LAMBDA=0.001)
    set_chi_env({"CHI_ROUTING": "xy", "CHI_LINK_LATENCY": "2", "CHI_LAMBDA": "0.001"})
    S.regen(0.001)
    print("Restored baseline chi_traffic (routing=xy, link_latency=2, vc_buf_size=2, LAMBDA=0.001)")


if __name__ == "__main__":
    main()
