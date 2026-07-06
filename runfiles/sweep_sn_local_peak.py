#!/usr/bin/env python3
"""SN terminal-link local inject/accept peaks (not end-to-end RN delivery).

Uses BookSim stats_out per-node sent_flits / accepted_flits to report, for the
4 SN nodes only:

  read ceiling  DAT CompData (SN source)  -> max sent_flits/cycle at SN  (inject)
  write ceiling DAT L3EvictData (SN dest)   -> max accepted_flits/cycle at SN (eject)
  both          REQ to SN                   -> max accepted_flits/cycle at SN (eject)

Also records the existing E2E DAT metrics from sweep_sn_throughput for contrast.

Output: ../doc/<SWEEP_OUT>  (default v6_repair_sn_local_peak.csv)
Env: SWEEP_OUT, SWEEP_BUFS, SWEEP_LAMBDAS, CHI_DATA_FLITS, plus CHI_* mix knobs.
"""
import csv
import os
import re
import subprocess

import sweep_sn_throughput as S

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(os.path.dirname(HERE), "doc")
CSV_OUT = os.path.join(DOC, os.environ.get("SWEEP_OUT", "v6_repair_sn_local_peak.csv"))
STATS_M = os.path.join(HERE, "sn_local_stats.m")

BASE = {
    "CHI_ROUTING": "xy",
    "CHI_LINK_LATENCY": "2",
    "CHI_DATA_FLITS": os.environ.get("CHI_DATA_FLITS", "2"),
}
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
DEFAULT_BUFS = [2, 8]
DEFAULT_LAMBDAS = [0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8]


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


def sn_nodes(txt):
    ids = re.findall(r"node(\d+)@", txt)
    return [int(x) for x in ids]


def class_labels(txt):
    labels = {}
    for m in re.finditer(
            r"^//\s*c(\d+)\s+(\S+)\s+(REQ|RSP|SNP|DAT)\s+(\w+)->(\w+)\s+size=(\d+)",
            txt, re.M):
        labels[int(m.group(1))] = {
            "name": m.group(2), "chan": m.group(3),
            "src": m.group(4), "dst": m.group(5), "size": int(m.group(6)),
        }
    return labels


def read_int_vec(txt, key):
    m = re.search(re.escape(key) + r"\s*=\s*\{([^}]*)\}", txt)
    return [int(x) for x in m.group(1).split(",")]


def class_roles(txt):
    """Return dat_read, dat_write, req_to_sn class ids."""
    labels = class_labels(txt)
    subnet = read_int_vec(txt, "class_subnet")
    sn = set(sn_nodes(txt))
    m = re.search(r"traffic\s*=\s*\{(.*?)\}\s*;", txt, re.S)
    dsts = re.findall(r"hotspot\(\{+([^{}]*)\}+\)", m.group(1))
    dat_read = dat_write = req_sn = None
    for c, lb in labels.items():
        if c >= len(subnet):
            continue
        dst = set(int(x) for x in dsts[c].split(",") if x.strip()) if c < len(dsts) else set()
        if subnet[c] == 3 and lb["src"] == "SN":      # DAT SN->RN
            dat_read = c
        if subnet[c] == 3 and dst == sn:              # DAT -> SN
            dat_write = c
        if subnet[c] == 0 and dst == sn:              # REQ -> SN
            req_sn = c
    return dat_read, dat_write, req_sn


def enable_stats_out():
    with open(S.CFG) as f:
        lines = f.readlines()
    out = [ln for ln in lines if not ln.strip().startswith("stats_out")]
    if out and not out[-1].endswith("\n"):
        out[-1] += "\n"
    out.append(f"stats_out = {STATS_M};\n")
    with open(S.CFG, "w") as f:
        f.writelines(out)


def parse_matlab_rates(path):
    """class_1based -> {sent: [per node], accepted: [per node]}."""
    txt = open(path).read()
    out = {}
    for kind in ("sent_flits", "accepted_flits"):
        for m in re.finditer(rf"{kind}\((\d+),:\)\s*=\s*\[([^\]]+)\]", txt):
            c = int(m.group(1)) - 1
            vec = [float(x) for x in m.group(2).split()]
            out.setdefault(c, {})[kind.split("_")[0]] = vec  # sent / accepted
    return out


def sn_stats(rates, cls, sn_ids):
    """Peak and mean flit/cycle over the 4 SN node indices."""
    if cls is None or cls not in rates:
        return None, None, None, None
    sent = rates[cls].get("sent")
    acc = rates[cls].get("accepted")
    s_vals = [sent[i] for i in sn_ids] if sent and max(sn_ids) < len(sent) else []
    a_vals = [acc[i] for i in sn_ids] if acc and max(sn_ids) < len(acc) else []
    s_max = max(s_vals) if s_vals else None
    s_avg = sum(s_vals) / len(s_vals) if s_vals else None
    a_max = max(a_vals) if a_vals else None
    a_avg = sum(a_vals) / len(a_vals) if a_vals else None
    return s_max, s_avg, a_max, a_avg


def run_once(lam, buf, mix_env):
    set_chi_env({**BASE, **mix_env, "CHI_VC_BUF_SIZE": str(buf)})
    S.regen(lam)
    enable_stats_out()
    with open(S.CFG) as f:
        txt = f.read()
    sn_ids = sn_nodes(txt)
    dat_read, dat_write, req_sn = class_roles(txt)
    nodes_m = re.search(r"=\s*(\d+)\s*nodes", txt)
    nodes = int(nodes_m.group(1)) if nodes_m else 172

    log = S.run_booksim()
    saturated = ("Simulation unstable" in log) or ("Aborting simulation" in log)
    stats = S.parse_overall(log)
    unstable = False
    if stats is None:
        stats = S.parse_last_display(log)
        unstable = True
    state = "UNSTBL" if unstable else ("SAT" if saturated else "ok")

    e2e_rd = e2e_wr = None
    if stats:
        read_cls, write_cls, nsn = S.class_meta()
        if mix_env is READ_MIX:
            e2e_rd = S.group(stats, read_cls, nodes, nsn)["util"]
        else:
            e2e_wr = S.group(stats, write_cls, nodes, nsn)["util"]

    rates = parse_matlab_rates(STATS_M) if os.path.exists(STATS_M) else {}

    if mix_env is READ_MIX:
        dat_cls = dat_read
        dat_sent_max, dat_sent_avg, _, _ = sn_stats(rates, dat_cls, sn_ids)
        _, _, req_acc_max, req_acc_avg = sn_stats(rates, req_sn, sn_ids)
        row_dat = ("read_dat_sent_max", dat_sent_max, dat_sent_avg, e2e_rd)
        row_req = ("read_req_acc_max", req_acc_max, req_acc_avg, None)
    else:
        dat_cls = dat_write
        _, _, dat_acc_max, dat_acc_avg = sn_stats(rates, dat_cls, sn_ids)
        _, _, req_acc_max, req_acc_avg = sn_stats(rates, req_sn, sn_ids)
        row_dat = ("write_dat_acc_max", dat_acc_max, dat_acc_avg, e2e_wr)
        row_req = ("write_req_acc_max", req_acc_max, req_acc_avg, None)

    return {
        "state": state, "lam": lam, "dat_cls": dat_cls, "req_cls": req_sn,
        "row_dat": row_dat, "row_req": row_req,
    }


def best_row(mix_name, buf, lambdas, mix_env):
    """Keep the lambda with highest SN-local DAT peak."""
    best = None
    for lam in lambdas:
        r = run_once(lam, buf, mix_env)
        peak = r["row_dat"][1]
        if peak is None:
            continue
        if best is None or peak > best["row_dat"][1]:
            best = {**r, "mix": mix_name, "buf": buf}
    return best


def main():
    bufs = parse_list("SWEEP_BUFS", DEFAULT_BUFS, int)
    lambdas = parse_list("SWEEP_LAMBDAS", DEFAULT_LAMBDAS, float)
    data_flits = os.environ.get("CHI_DATA_FLITS", "2")

    rows = []
    print(f"{'mix':>5} {'buf':>3} {'lam':>5} {'st':>6} | "
          f"{'SNlocalDAT':>10} {'SNavgDAT':>8} {'E2Eutil':>8} | "
          f"{'SNlocalREQ':>10} {'SNavgREQ':>8}")
    for buf in bufs:
        for mix_name, mix_env in (("read", READ_MIX), ("write", WRITE_MIX)):
            b = best_row(mix_name, buf, lambdas, mix_env)
            if not b:
                continue
            pk, av, e2e = b["row_dat"][1], b["row_dat"][2], b["row_dat"][3]
            rpk, rav = b["row_req"][1], b["row_req"][2]
            print(f"{mix_name:>5} {buf:>3} {b['lam']:>5.3f} {b['state']:>6} | "
                  f"{(pk or 0):10.4f} {(av or 0):8.4f} {(e2e or 0):8.1%} | "
                  f"{(rpk or 0):10.4f} {(rav or 0):8.4f}")
            rows.append([
                mix_name, buf, data_flits, b["lam"], b["state"],
                b["dat_cls"], b["req_cls"],
                pk, av, e2e,
                rpk, rav,
                b["row_dat"][0], b["row_req"][0],
            ])

    os.makedirs(DOC, exist_ok=True)
    with open(CSV_OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "mix", "vc_buf_size", "data_flits", "lambda", "state",
            "dat_class", "req_sn_class",
            "sn_dat_peak", "sn_dat_avg", "e2e_dat_util",
            "sn_req_peak", "sn_req_avg",
            "dat_metric", "req_metric",
        ])
        w.writerows(rows)
    print(f"\nWrote {CSV_OUT} ({len(rows)} rows)")

    set_chi_env({"CHI_ROUTING": "xy", "CHI_LINK_LATENCY": "2",
                 "CHI_VC_BUF_SIZE": "2", "CHI_LAMBDA": "0.001"})
    S.regen(0.001)
    if os.path.exists(STATS_M):
        os.remove(STATS_M)
    print("Restored baseline chi_traffic")


if __name__ == "__main__":
    main()
