#!/usr/bin/env python3
"""Injection-rate sweep focused on SN (DDR) read/write data throughput.

Unlike sweep_chi_subnet.py (which aggregates by CHI channel/subnet), this script
isolates the SN memory-data path and reports, per offered load:

  * read  data throughput  = DAT classes whose SOURCE is the SN set (SN->RN
                             CompData_DMT); this is data leaving the SNs.
  * write data throughput  = DAT classes whose DESTINATION is the SN set
                             (HN->SN L3EvictData / CleanInvalidWriteback); this
                             is data absorbed by the SNs.

SN classes are auto-detected from the generated config (class_subnet +
class_source + traffic hotspot sets), so the script keeps working if the traffic
ratios (and therefore the class layout) change.

BookSim per-class "accepted flit rate average" is normalised by the node count
(rate = flits / cycle / _nodes), so absolute network flit/cycle = rate * _nodes,
and per-SN flit/cycle = that / (number of SN nodes).

Saturated runs (latency diverges, no Overall block) fall back to the last
periodic DisplayStats snapshot so the plateau throughput is still captured.

Output: ../doc/<SWEEP_OUT>  (default v6_sn_throughput_current.csv).
Env: SWEEP_LAMBDAS, SWEEP_OUT, plus all CHI_* knobs are passed to gen_chi_traffic.
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
CSV_OUT = os.path.join(DOC, os.environ.get("SWEEP_OUT", "v6_sn_throughput_current.csv"))

# structural ceiling of one SN terminal link (1 flit / cycle, full-duplex).
LINK_CEILING = 1.0

DEFAULT_LAMBDAS = [0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.008, 0.010]


def lambdas():
    env = os.environ.get("SWEEP_LAMBDAS")
    if env:
        return [float(x) for x in env.replace(",", " ").split()]
    return DEFAULT_LAMBDAS


# how many consecutive saturated/unstable points to collect before stopping.
# For a ceiling sweep the SN link saturates well after the network goes unstable,
# so raise this (e.g. 99) to keep pushing offered load until the SN data
# throughput itself plateaus.
MAX_UNSTBL = int(os.environ.get("SWEEP_MAX_UNSTBL", 2))


def regen(lam):
    env = dict(os.environ, CHI_LAMBDA=repr(lam))
    subprocess.run(["python3", GEN], env=env, cwd=HERE,
                   capture_output=True, check=True)


def read_int_vec(txt, key):
    m = re.search(re.escape(key) + r"\s*=\s*\{([^}]*)\}", txt)
    if not m:
        raise RuntimeError(f"{key} not found in config")
    return [int(x) for x in m.group(1).split(",")]


def read_class_source(txt):
    """class_source = {{..},{..},...}; -> list of node-id sets (one per class)."""
    m = re.search(r"class_source\s*=\s*\{(.*?)\}\s*;", txt, re.S)
    if not m:
        raise RuntimeError("class_source not found in config")
    inner = m.group(1)
    sets = re.findall(r"\{([^{}]*)\}", inner)
    return [set(int(x) for x in s.split(",") if x.strip()) for s in sets]


def read_traffic_dst(txt):
    """traffic = {hotspot({..}),...}; -> list of destination node-id sets."""
    m = re.search(r"traffic\s*=\s*\{(.*?)\}\s*;", txt, re.S)
    if not m:
        raise RuntimeError("traffic not found in config")
    # tolerate both hotspot({..}) and the correct double-brace hotspot({{..}})
    dsts = re.findall(r"hotspot\(\{+([^{}]*)\}+\)", m.group(1))
    return [set(int(x) for x in s.split(",") if x.strip()) for s in dsts]


def sn_nodes(txt):
    """Parse the 'SN placement' comment: R#=node168@(...)."""
    ids = re.findall(r"node(\d+)@", txt)
    return set(int(x) for x in ids)


def class_meta():
    with open(CFG) as f:
        txt = f.read()
    subnet = read_int_vec(txt, "class_subnet")
    csrc = read_class_source(txt)
    cdst = read_traffic_dst(txt)
    sn = sn_nodes(txt)
    dat = 3  # REQ=0 RSP=1 SNP=2 DAT=3
    read_cls = [c for c in range(len(subnet))
                if subnet[c] == dat and csrc[c] == sn]      # SN -> RN data
    write_cls = [c for c in range(len(subnet))
                 if subnet[c] == dat and cdst[c] == sn]     # HN -> SN data
    return read_cls, write_cls, len(sn)


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
        "inj_flit": r"Injected flit rate average = ([0-9.eE+-]+)",
        "acc_flit": r"Accepted flit rate average = ([0-9.eE+-]+)",
    }
    for m in block_re.finditer(tail):
        c = int(m.group(1))
        body = m.group(2)
        row = {}
        for key, pat in fields.items():
            mm = re.search(pat, body)
            row[key] = None if (not mm or mm.group(1).lower() == "nan") else float(mm.group(1))
        out[c] = row
    return out


def parse_last_display(log):
    """Recover the last periodic DisplayStats snapshot from a diverged run."""
    field_pat = {
        "plat": re.compile(r"^Packet latency average = ([0-9.eE+-]+|nan)"),
        "inj_flit": re.compile(r"^Injected flit rate average = ([0-9.eE+-]+)"),
        "acc_flit": re.compile(r"^Accepted flit rate average\s*=\s*([0-9.eE+-]+)"),
    }
    class_re = re.compile(r"^Class (\d+):\s*$")
    out = {}
    cur = None
    for line in log.splitlines():
        m = class_re.match(line)
        if m:
            cur = int(m.group(1))
            continue
        if cur is None:
            continue
        for key, pat in field_pat.items():
            mm = pat.match(line)
            if mm:
                v = mm.group(1)
                out.setdefault(cur, {})[key] = None if v.lower() == "nan" else float(v)
                break
    if not any("acc_flit" in r for r in out.values()):
        return None
    return out


def wavg(stats, classes, val_key, w_key):
    num = den = 0.0
    for c in classes:
        r = stats.get(c, {})
        v, w = r.get(val_key), r.get(w_key)
        if v is None or w is None or w <= 0:
            continue
        num += v * w
        den += w
    return num / den if den > 0 else None


def group(stats, classes, nodes, nsn):
    """Absolute (all-4-SN) and per-SN flit/cycle for a class group."""
    acc = sum((stats.get(c, {}).get("acc_flit") or 0.0) for c in classes) * nodes
    inj = sum((stats.get(c, {}).get("inj_flit") or 0.0) for c in classes) * nodes
    return {
        "acc_total": acc,
        "acc_per_sn": acc / nsn if nsn else 0.0,
        "inj_total": inj,
        "inj_per_sn": inj / nsn if nsn else 0.0,
        "plat": wavg(stats, classes, "plat", "acc_flit"),
        "util": (acc / nsn / LINK_CEILING) if nsn else 0.0,
    }


def main():
    # node count from the topology (routers*PER + SN); read from config comment.
    with open(CFG) as f:
        head = f.read()
    mnodes = re.search(r"=\s*(\d+)\s*nodes", head)
    nodes = int(mnodes.group(1)) if mnodes else 172

    rows = []
    sat_streak = 0
    print(f"{'lambda':>8} {'state':>7} | "
          f"{'rd/SN':>8} {'rd tot':>8} {'rd util':>7} | "
          f"{'wr/SN':>8} {'wr tot':>8} {'wr util':>7}")
    for lam in lambdas():
        regen(lam)
        read_cls, write_cls, nsn = class_meta()
        try:
            log = run_booksim()
        except subprocess.TimeoutExpired:
            print(f"{lam:>8} {'TIMO':>7} |")
            sat_streak += 1
            if sat_streak >= MAX_UNSTBL:
                break
            continue
        saturated = ("Simulation unstable" in log) or ("Aborting simulation" in log)
        stats = parse_overall(log)
        unstable = False
        if stats is None:
            stats = parse_last_display(log)
            unstable = True
        if stats is None:
            print(f"{lam:>8} {'NODATA':>7} |")
            sat_streak += 1
            if sat_streak >= MAX_UNSTBL:
                break
            continue
        rd = group(stats, read_cls, nodes, nsn)
        wr = group(stats, write_cls, nodes, nsn)
        state = "UNSTBL" if unstable else ("SAT" if saturated else "ok")
        print(f"{lam:>8} {state:>7} | "
              f"{rd['acc_per_sn']:8.4f} {rd['acc_total']:8.4f} {rd['util']:6.1%} | "
              f"{wr['acc_per_sn']:8.4f} {wr['acc_total']:8.4f} {wr['util']:6.1%}")
        rows.append([
            lam, state, nsn,
            rd["acc_per_sn"], rd["acc_total"], rd["inj_per_sn"], rd["inj_total"],
            rd["util"], rd["plat"],
            wr["acc_per_sn"], wr["acc_total"], wr["inj_per_sn"], wr["inj_total"],
            wr["util"], wr["plat"],
        ])
        if saturated:
            sat_streak += 1
            if sat_streak >= MAX_UNSTBL:
                print(f"  -> {MAX_UNSTBL} saturated points collected, stopping sweep")
                break
        else:
            sat_streak = 0

    os.makedirs(DOC, exist_ok=True)
    with open(CSV_OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "lambda", "state", "n_sn",
            "read_acc_per_sn", "read_acc_total", "read_inj_per_sn", "read_inj_total",
            "read_util", "read_plat",
            "write_acc_per_sn", "write_acc_total", "write_inj_per_sn", "write_inj_total",
            "write_util", "write_plat",
        ])
        w.writerows(rows)
    print(f"\nWrote {CSV_OUT} ({len(rows)} rows)")

    # restore the persisted baseline (latency=2, XY, default ratios, LAMBDA=0.001)
    # without inheriting any CHI_* ratio overrides used by a focused experiment.
    base_env = {k: v for k, v in os.environ.items()
                if not (k.startswith("CHI_") or k in ("SWEEP_OUT", "SWEEP_LAMBDAS"))}
    base_env.update(CHI_ROUTING="xy", CHI_LINK_LATENCY="2", CHI_LAMBDA="0.001")
    subprocess.run(["python3", GEN], env=base_env, cwd=HERE,
                   capture_output=True, check=True)
    print("Restored baseline chi_traffic (routing=xy, link_latency=2, CHI_LAMBDA=0.001)")


if __name__ == "__main__":
    main()
