#!/usr/bin/env python3
"""SN terminal-link local inject/accept peaks (not end-to-end RN delivery).

Uses BookSim stats_out per-node sent_flits / accepted_flits to report, for the
4 SN nodes only:

  read ceiling  DAT CompData (SN source)  -> max sent_flits/cycle at SN  (inject)
  write ceiling DAT L3EvictData (SN dest)   -> max accepted_flits/cycle at SN (eject)
  both          REQ to SN                   -> max accepted_flits/cycle at SN (eject)

Also records optional E2E DAT metrics parsed from the BookSim log.
If sn_local_stats.m is missing/incomplete, falls back to log-based E2E util
(peak=avg) so the CSV is not left header-only.

Output: ../doc/<SWEEP_OUT>  (default v6_repair_sn_local_peak.csv) — best λ per mix/buf
         ../doc/<SWEEP_ALL_OUT or {SWEEP_OUT stem}_sweep.csv> — all λ points
         ../doc/stats_out/<mix>_buf<N>_D<D>_lam<L>_sn_local_stats.m  (best λ only)
Env: SWEEP_OUT, SWEEP_ALL_OUT, SWEEP_STATS_DIR, SWEEP_BUFS, SWEEP_LAMBDAS, CHI_DATA_FLITS, plus CHI_* mix knobs.
"""
import csv
import os
import re
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOOKSIM = os.path.join(ROOT, "src", "booksim")
GEN = os.path.join(HERE, "gen_chi_traffic.py")
CFG = os.path.join(HERE, "chi_traffic")
DOC = os.path.join(ROOT, "doc")
CSV_OUT = os.path.join(DOC, os.environ.get("SWEEP_OUT", "v6_repair_sn_local_peak.csv"))
_all_default = os.path.splitext(os.environ.get("SWEEP_OUT", "v6_repair_sn_local_peak.csv"))[0] + "_sweep.csv"
ALL_CSV_OUT = os.path.join(DOC, os.environ.get("SWEEP_ALL_OUT", _all_default))
STATS_OUT_DIR = os.path.join(DOC, os.environ.get("SWEEP_STATS_DIR", "stats_out"))
STATS_M = os.path.join(HERE, "sn_local_stats.m")

LINK_CEILING = 1.0  # one SN terminal link = 1 flit/cycle

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
# Keep defaults in the linear/knee region after CHI_NODE_NORMALIZE (SN inject ×21).
# High λ (0.1–0.8) often abort before WriteStats finishes on slower machines.
DEFAULT_LAMBDAS = [0.005, 0.01, 0.015, 0.02, 0.025, 0.03]


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


def regen(lam):
    env = dict(os.environ, CHI_LAMBDA=repr(lam))
    p = subprocess.run(["python3", GEN], env=env, cwd=HERE,
                       capture_output=True, text=True)
    if p.returncode != 0:
        err = (p.stderr or p.stdout or "").strip().splitlines()
        tail = "\n".join(err[-20:]) if err else "(no output)"
        raise RuntimeError(f"gen_chi_traffic.py failed (rc={p.returncode}):\n{tail}")


def run_booksim():
    if not os.path.isfile(BOOKSIM) or not os.access(BOOKSIM, os.X_OK):
        raise FileNotFoundError(
            f"BookSim binary missing or not executable: {BOOKSIM}\n"
            "Build it with: cd src && make")
    try:
        p = subprocess.run([BOOKSIM, "chi_traffic"], cwd=HERE,
                           capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "")
        print(f"  ! booksim TIMEOUT after 600s; log tail:\n"
              + "\n".join(out.strip().splitlines()[-15:]), flush=True)
        return out, -1, True
    return p.stdout + p.stderr, p.returncode, False


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
    dsts = re.findall(r"hotspot\(\{+([^{}]*)\}+\)", m.group(1))
    return [set(int(x) for x in s.split(",") if x.strip()) for s in dsts]


def sn_node_set(txt):
    """Parse SN node ids from the placement comment: R#=node168@(...)."""
    return set(int(x) for x in re.findall(r"node(\d+)@", txt))


def class_meta():
    with open(CFG) as f:
        txt = f.read()
    subnet = read_int_vec(txt, "class_subnet")
    csrc = read_class_source(txt)
    cdst = read_traffic_dst(txt)
    sn = sn_node_set(txt)
    dat = 3  # REQ=0 RSP=1 SNP=2 DAT=3
    read_cls = [c for c in range(len(subnet))
                if subnet[c] == dat and csrc[c] == sn]
    write_cls = [c for c in range(len(subnet))
                 if subnet[c] == dat and cdst[c] == sn]
    return read_cls, write_cls, len(sn)


def parse_overall(log):
    if "Overall Traffic Statistics" not in log:
        return None
    tail = log.split("Overall Traffic Statistics")[-1]
    out = {}
    block_re = re.compile(
        r"====== Traffic class (\d+) ======(.*?)"
        r"(?======= Traffic class|Total run time|$)", re.S)
    fields = {
        "flat": r"Flit latency average = ([0-9.eE+-]+|nan)",
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
        "flat": re.compile(r"^Flit latency average = ([0-9.eE+-]+|nan)"),
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
        "flat": wavg(stats, classes, "flat", "acc_flit"),
        "util": (acc / nsn / LINK_CEILING) if nsn else 0.0,
    }


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
    if not m:
        raise RuntimeError(f"{key} not found in config")
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
    """Force stats_out to a relative path under runfiles/ (cwd of booksim)."""
    with open(CFG) as f:
        lines = f.readlines()
    out = [ln for ln in lines if not ln.strip().startswith("stats_out")]
    if out and not out[-1].endswith("\n"):
        out[-1] += "\n"
    # Relative path: booksim runs with cwd=HERE, so this always lands in runfiles/.
    out.append("stats_out = sn_local_stats.m;\n")
    with open(CFG, "w") as f:
        f.writelines(out)


def parse_matlab_rates(path):
    """class_1based -> {sent: [per node], accepted: [per node]}."""
    if not os.path.exists(path):
        return {}, "missing"
    txt = open(path).read()
    if "sent_flits(" not in txt and "accepted_flits(" not in txt:
        return {}, "header_only"
    out = {}
    for kind in ("sent_flits", "accepted_flits"):
        for m in re.finditer(rf"{kind}\((\d+),:\)\s*=\s*\[([^\]]+)\]", txt):
            c = int(m.group(1)) - 1
            vec = [float(x) for x in m.group(2).split()]
            out.setdefault(c, {})[kind.split("_")[0]] = vec  # sent / accepted
    if not out:
        return {}, "unparsed"
    return out, "ok"


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


def log_fallback_metrics(stats, mix_env, nodes, nsn):
    """When sn_local_stats.m is unusable, approximate SN DAT/REQ from log rates.

    Log rates are network-wide averages (flits/cycle/node). Convert to per-SN
    util the same way as sweep_sn_throughput.group(). Peak is set equal to avg
    because the log has no per-node breakdown.
    """
    if not stats or nsn <= 0:
        return None, None, None, None
    read_cls, write_cls, _ = class_meta()
    if mix_env is READ_MIX:
        g = group(stats, read_cls, nodes, nsn)
    else:
        g = group(stats, write_cls, nodes, nsn)
    util = g["util"]
    # No per-node peak in the log; use avg for both so selection still works.
    return util, util, None, None


def diagnose_skip(lam, mix_name, buf, reason, extra=""):
    msg = f"  ! skip {mix_name} buf={buf} lam={lam:g}: {reason}"
    if extra:
        msg += f" ({extra})"
    print(msg, flush=True)


def run_once(lam, buf, mix_env):
    mix_name = "read" if mix_env is READ_MIX else "write"
    set_chi_env({**BASE, **mix_env, "CHI_VC_BUF_SIZE": str(buf)})
    regen(lam)
    enable_stats_out()
    # Drop stale stats from a previous λ so we never parse an old file by mistake.
    if os.path.exists(STATS_M):
        os.remove(STATS_M)

    with open(CFG) as f:
        txt = f.read()
    sn_ids = sn_nodes(txt)
    dat_read, dat_write, req_sn = class_roles(txt)
    nodes_m = re.search(r"=\s*(\d+)\s*nodes", txt)
    nodes = int(nodes_m.group(1)) if nodes_m else 172

    if not sn_ids:
        diagnose_skip(lam, mix_name, buf, "no SN nodes in chi_traffic comment")
    if mix_env is READ_MIX and dat_read is None:
        diagnose_skip(lam, mix_name, buf, "DAT SN->RN class not found (class_roles)")
    if mix_env is not READ_MIX and dat_write is None:
        diagnose_skip(lam, mix_name, buf, "DAT->SN class not found (class_roles)")

    log, rc, timed_out = run_booksim()
    saturated = ("Simulation unstable" in log) or ("Aborting simulation" in log)
    stats = parse_overall(log)
    unstable = False
    if stats is None:
        stats = parse_last_display(log)
        unstable = True
    if timed_out:
        state = "TIMO"
    elif rc != 0 and not saturated:
        state = f"RC{rc}"
        diagnose_skip(lam, mix_name, buf, f"booksim rc={rc}",
                      "log tail: " + " | ".join(log.strip().splitlines()[-3:]))
    else:
        state = "UNSTBL" if unstable else ("SAT" if saturated else "ok")

    e2e_rd = e2e_wr = None
    read_cls = write_cls = []
    nsn = len(sn_ids) or 4
    if stats:
        read_cls, write_cls, nsn_meta = class_meta()
        nsn = nsn_meta or nsn
        if mix_env is READ_MIX:
            e2e_rd = group(stats, read_cls, nodes, nsn)["util"]
        else:
            e2e_wr = group(stats, write_cls, nodes, nsn)["util"]

    rates, stats_status = parse_matlab_rates(STATS_M)
    used_fallback = False

    if mix_env is READ_MIX:
        dat_cls = dat_read
        dat_sent_max, dat_sent_avg, _, _ = sn_stats(rates, dat_cls, sn_ids)
        _, _, req_acc_max, req_acc_avg = sn_stats(rates, req_sn, sn_ids)
        if dat_sent_avg is None:
            fb_peak, fb_avg, _, _ = log_fallback_metrics(stats, mix_env, nodes, nsn)
            if fb_avg is not None:
                dat_sent_max, dat_sent_avg = fb_peak, fb_avg
                used_fallback = True
                diagnose_skip(lam, mix_name, buf,
                              f"stats_out={stats_status}; using log fallback",
                              f"e2e_util={fb_avg:.4f}")
            else:
                diagnose_skip(lam, mix_name, buf,
                              f"no SN DAT avg (stats_out={stats_status}, "
                              f"dat_cls={dat_cls}, sn={sn_ids})")
        row_dat = ("read_dat_sent_max", dat_sent_max, dat_sent_avg, e2e_rd)
        row_req = ("read_req_acc_max", req_acc_max, req_acc_avg, None)
    else:
        dat_cls = dat_write
        _, _, dat_acc_max, dat_acc_avg = sn_stats(rates, dat_cls, sn_ids)
        _, _, req_acc_max, req_acc_avg = sn_stats(rates, req_sn, sn_ids)
        if dat_acc_avg is None:
            fb_peak, fb_avg, _, _ = log_fallback_metrics(stats, mix_env, nodes, nsn)
            if fb_avg is not None:
                dat_acc_max, dat_acc_avg = fb_peak, fb_avg
                used_fallback = True
                diagnose_skip(lam, mix_name, buf,
                              f"stats_out={stats_status}; using log fallback",
                              f"e2e_util={fb_avg:.4f}")
            else:
                diagnose_skip(lam, mix_name, buf,
                              f"no SN DAT avg (stats_out={stats_status}, "
                              f"dat_cls={dat_cls}, sn={sn_ids})")
        row_dat = ("write_dat_acc_max", dat_acc_max, dat_acc_avg, e2e_wr)
        row_req = ("write_req_acc_max", req_acc_max, req_acc_avg, None)

    return {
        "state": state, "lam": lam, "dat_cls": dat_cls, "req_cls": req_sn,
        "row_dat": row_dat, "row_req": row_req,
        "used_fallback": used_fallback, "stats_status": stats_status,
    }


def stats_archive_name(mix_name, buf, lam, data_flits):
    lam_s = f"{lam:g}".replace(".", "p")
    return f"{mix_name}_buf{buf}_D{data_flits}_lam{lam_s}_sn_local_stats.m"


def sweep_mix(mix_name, buf, lambdas, mix_env, stats_dir, data_flits):
    """Run all lambdas; archive stats_out for best SN-local DAT avg only."""
    best = None
    all_rows = []
    n_skip = 0
    for lam in lambdas:
        r = run_once(lam, buf, mix_env)
        peak = r["row_dat"][1]
        avg = r["row_dat"][2]
        e2e = r["row_dat"][3]
        rpk = r["row_req"][1]
        rav = r["row_req"][2]
        if avg is None:
            n_skip += 1
            continue
        all_rows.append({
            "mix": mix_name, "buf": buf, "data_flits": data_flits,
            "lam": lam, "state": r["state"],
            "dat_cls": r["dat_cls"], "req_cls": r["req_cls"],
            "sn_dat_peak": peak, "sn_dat_avg": avg, "e2e_dat_util": e2e,
            "sn_req_peak": rpk, "sn_req_avg": rav,
            "dat_metric": r["row_dat"][0], "req_metric": r["row_req"][0],
            "stats_file": "",
            "used_fallback": r.get("used_fallback", False),
        })
        if best is None or avg > best["sn_dat_avg"]:
            if best and best.get("stats_path"):
                try:
                    os.remove(best["stats_path"])
                except OSError:
                    pass
            stats_name = stats_archive_name(mix_name, buf, lam, data_flits)
            stats_path = os.path.join(stats_dir, stats_name)
            stats_file = ""
            if os.path.exists(STATS_M) and not r.get("used_fallback"):
                shutil.copy2(STATS_M, stats_path)
                stats_file = os.path.join(os.path.basename(stats_dir), stats_name)
            best = {
                **all_rows[-1],
                "stats_file": stats_file,
                "stats_path": stats_path if stats_file else None,
            }
    if best:
        if "stats_path" in best:
            del best["stats_path"]
        for row in all_rows:
            if row["lam"] == best["lam"]:
                row["stats_file"] = best.get("stats_file", "")
                break
    elif n_skip:
        print(f"  ! {mix_name} buf={buf}: all {n_skip} lambda(s) skipped "
              f"(no usable SN DAT avg)", flush=True)
    return best, all_rows


def main():
    if not os.path.isfile(BOOKSIM) or not os.access(BOOKSIM, os.X_OK):
        raise SystemExit(
            f"BookSim binary missing or not executable: {BOOKSIM}\n"
            "Build it with: cd src && make")

    bufs = parse_list("SWEEP_BUFS", DEFAULT_BUFS, int)
    lambdas = parse_list("SWEEP_LAMBDAS", DEFAULT_LAMBDAS, float)
    data_flits = os.environ.get("CHI_DATA_FLITS", "2")
    print(f"booksim={BOOKSIM}")
    print(f"bufs={bufs} lambdas={lambdas} data_flits={data_flits}")
    print(f"stats_out target={STATS_M}")

    os.makedirs(STATS_OUT_DIR, exist_ok=True)
    for fn in os.listdir(STATS_OUT_DIR):
        if fn.endswith("_sn_local_stats.m"):
            os.remove(os.path.join(STATS_OUT_DIR, fn))
    rows = []
    sweep_rows = []
    print(f"{'mix':>5} {'buf':>3} {'lam':>5} {'st':>6} | "
          f"{'SNlocalDAT':>10} {'SNavgDAT':>8} {'E2Eutil':>8} | "
          f"{'SNlocalREQ':>10} {'SNavgREQ':>8}")
    for buf in bufs:
        for mix_name, mix_env in (("read", READ_MIX), ("write", WRITE_MIX)):
            b, all_pts = sweep_mix(mix_name, buf, lambdas, mix_env, STATS_OUT_DIR, data_flits)
            sweep_rows.extend(all_pts)
            if not b:
                continue
            pk, av, e2e = b["sn_dat_peak"], b["sn_dat_avg"], b["e2e_dat_util"]
            rpk, rav = b["sn_req_peak"], b["sn_req_avg"]
            fb = " [log]" if b.get("used_fallback") else ""
            print(f"{mix_name:>5} {buf:>3} {b['lam']:>5.3f} {b['state']:>6} | "
                  f"{(pk or 0):10.4f} {(av or 0):8.4f} {(e2e or 0):8.1%} | "
                  f"{(rpk or 0):10.4f} {(rav or 0):8.4f}{fb}")
            rows.append([
                mix_name, buf, data_flits, b["lam"], b["state"],
                b["dat_cls"], b["req_cls"],
                pk, av, e2e,
                rpk, rav,
                b["dat_metric"], b["req_metric"],
                b.get("stats_file", ""),
            ])

    header = [
        "mix", "vc_buf_size", "data_flits", "lambda", "state",
        "dat_class", "req_sn_class",
        "sn_dat_peak", "sn_dat_avg", "e2e_dat_util",
        "sn_req_peak", "sn_req_avg",
        "dat_metric", "req_metric",
        "stats_file",
    ]
    def to_csv_row(r):
        return [
            r["mix"], r["buf"], r["data_flits"], r["lam"], r["state"],
            r["dat_cls"], r["req_cls"],
            r["sn_dat_peak"], r["sn_dat_avg"], r["e2e_dat_util"],
            r["sn_req_peak"], r["sn_req_avg"],
            r["dat_metric"], r["req_metric"],
            r.get("stats_file", ""),
        ]

    os.makedirs(DOC, exist_ok=True)
    with open(CSV_OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"\nWrote {CSV_OUT} ({len(rows)} rows)")
    with open(ALL_CSV_OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(to_csv_row(r) for r in sweep_rows)
    print(f"Wrote {ALL_CSV_OUT} ({len(sweep_rows)} rows)")
    print(f"Archived stats_out -> {STATS_OUT_DIR}/")
    if not rows:
        print("WARNING: peak CSV has header only — every lambda was skipped.\n"
              "  Check messages above (stats_out=missing/header_only, booksim rc, "
              "class_roles). Prefer SWEEP_LAMBDAS in 0.005–0.03.")

    set_chi_env({"CHI_ROUTING": "xy", "CHI_LINK_LATENCY": "2",
                 "CHI_VC_BUF_SIZE": "2", "CHI_LAMBDA": "0.001"})
    regen(0.001)
    if os.path.exists(STATS_M):
        os.remove(STATS_M)
    print("Restored baseline chi_traffic")


if __name__ == "__main__":
    main()
