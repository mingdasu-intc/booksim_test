#!/usr/bin/env python3
"""Quantify where the SN throughput bottleneck is for the current chi_traffic.

Runs booksim on the already-generated ./chi_traffic and reports, from the last
statistics snapshot (Overall block if converged, else last periodic DisplayStats
for a saturated run):

  * per class: injected/accepted flit rate (avg) and the PEAK per-node injected
    and accepted flit rate with the node id -> peak link utilisation (1 flit/cyc);
  * per subnet (REQ/RSP/SNP/DAT): accepted/injected and accept ratio + latency.

The class -> (channel, src, dst) mapping is parsed from the config comment header
so the labels track whatever traffic mix is currently generated.

Usage: python3 analyze_bottleneck.py [tag]
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOOKSIM = os.path.join(ROOT, "src", "booksim")
CFG = os.path.join(HERE, "chi_traffic")
TAG = sys.argv[1] if len(sys.argv) > 1 else "run"
SUBNET_NAME = {0: "REQ", 1: "RSP", 2: "SNP", 3: "DAT"}


def read_int_vec(txt, key):
    m = re.search(re.escape(key) + r"\s*=\s*\{([^}]*)\}", txt)
    return [int(x) for x in m.group(1).split(",")]


def class_labels(txt):
    """Parse '//   cN cat.sub.msg CHAN SRC->DST size=..' comment lines."""
    labels = {}
    for m in re.finditer(
            r"^//\s*c(\d+)\s+(\S+)\s+(REQ|RSP|SNP|DAT)\s+(\w+)->(\w+)\s+size=(\d+)",
            txt, re.M):
        labels[int(m.group(1))] = {
            "name": m.group(2), "chan": m.group(3),
            "src": m.group(4), "dst": m.group(5), "size": int(m.group(6)),
        }
    return labels


def run_booksim():
    p = subprocess.run([BOOKSIM, "chi_traffic"], cwd=HERE,
                       capture_output=True, text=True, timeout=600)
    return p.stdout + p.stderr


def parse_snapshot(log):
    """Last per-class snapshot: avg + peak(node) for inj/acc flit rate, + flat.

    Works on both the periodic DisplayStats blocks and the Overall block (same
    field layout); later blocks overwrite earlier so we end on the last one.
    """
    out = {}
    cur = None
    pending = None  # which metric's following 'maximum' line to capture
    class_re = re.compile(r"^(?:Class|====== Traffic class) (\d+)")
    avg_re = {
        "inj_flit": re.compile(r"^Injected flit rate average\s*=\s*([0-9.eE+-]+)"),
        "acc_flit": re.compile(r"^Accepted flit rate average\s*=\s*([0-9.eE+-]+)"),
        "flat": re.compile(r"^Flit latency average\s*=\s*([0-9.eE+-]+|nan)"),
    }
    max_re = re.compile(r"^\s*maximum\s*=\s*([0-9.eE+-]+)\s*\(at node (\d+)\)")
    for line in log.splitlines():
        m = class_re.match(line)
        if m:
            cur = int(m.group(1))
            out.setdefault(cur, {})
            pending = None
            continue
        if cur is None:
            continue
        hit = False
        for key, rx in avg_re.items():
            mm = rx.match(line)
            if mm:
                v = mm.group(1)
                out[cur][key] = None if v.lower() == "nan" else float(v)
                pending = key if key in ("inj_flit", "acc_flit") else None
                hit = True
                break
        if hit:
            continue
        mm = max_re.match(line)
        if mm and pending:
            out[cur][pending + "_max"] = float(mm.group(1))
            out[cur][pending + "_max_node"] = int(mm.group(2))
            pending = None
    return out


def main():
    with open(CFG) as f:
        txt = f.read()
    labels = class_labels(txt)
    subnet = read_int_vec(txt, "class_subnet")
    mnodes = re.search(r"=\s*(\d+)\s*nodes", txt)
    nodes = int(mnodes.group(1)) if mnodes else 172
    mlam = re.search(r"LAMBDA=([0-9.eE+-]+)", txt)
    lam = mlam.group(1) if mlam else "?"

    log = run_booksim()
    converged = "Overall Traffic Statistics" in log
    stats = parse_snapshot(log)

    print(f"\n===== bottleneck analysis [{TAG}]  LAMBDA={lam}  "
          f"{'converged' if converged else 'SATURATED (last snapshot)'} =====")
    print(f"{'cls':>3} {'message':<26} {'chan':>4} {'src->dst':>9} {'sz':>2} "
          f"{'inj_avg':>8} {'acc_avg':>8} {'acc/inj':>7} "
          f"{'injPeak(node)':>15} {'accPeak(node)':>15} {'flat':>7}")
    subn = {}
    for c in sorted(stats):
        s = stats[c]
        lb = labels.get(c, {"name": f"class{c}", "chan": SUBNET_NAME[subnet[c]],
                            "src": "?", "dst": "?", "size": 1})
        inj = s.get("inj_flit") or 0.0
        acc = s.get("acc_flit") or 0.0
        ratio = acc / inj if inj > 0 else 0.0
        ipk = s.get("inj_flit_max"); ipn = s.get("inj_flit_max_node")
        apk = s.get("acc_flit_max"); apn = s.get("acc_flit_max_node")
        print(f"{c:>3} {lb['name']:<26} {lb['chan']:>4} "
              f"{lb['src']+'->'+lb['dst']:>9} {lb['size']:>2} "
              f"{inj:8.4f} {acc:8.4f} {ratio:7.2%} "
              f"{(ipk or 0):9.3f}({ipn if ipn is not None else '-':>3}) "
              f"{(apk or 0):9.3f}({apn if apn is not None else '-':>3}) "
              f"{(s.get('flat') or 0):7.1f}")
        ch = SUBNET_NAME[subnet[c]]
        d = subn.setdefault(ch, {"inj": 0.0, "acc": 0.0, "lat_num": 0.0, "lat_den": 0.0})
        d["inj"] += inj
        d["acc"] += acc
        if s.get("flat") is not None:
            d["lat_num"] += s["flat"] * acc
            d["lat_den"] += acc

    print(f"\n{'subnet':>6} {'inj(net)':>9} {'acc(net)':>9} {'acc/inj':>7} {'wlat':>7}")
    for ch in ("REQ", "RSP", "SNP", "DAT"):
        if ch not in subn:
            continue
        d = subn[ch]
        ratio = d["acc"] / d["inj"] if d["inj"] > 0 else 0.0
        wlat = d["lat_num"] / d["lat_den"] if d["lat_den"] > 0 else 0.0
        print(f"{ch:>6} {d['inj']*nodes:9.4f} {d['acc']*nodes:9.4f} "
              f"{ratio:7.2%} {wlat:7.1f}")
    print("\nnote: injPeak/accPeak are per-node flit rates (1.0 = terminal link "
          "fully used). A class whose peak sits at an SN node near 1.0 means that "
          "SN link is the limiter; low peaks everywhere mean the mesh/flow is.")


if __name__ == "__main__":
    main()
