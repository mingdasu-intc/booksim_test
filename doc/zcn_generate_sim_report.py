#!/usr/bin/env python3
"""ZCN scenario report: vc_buf=4, DATA_FLITS=2, SN read/write utilization.

Inputs (doc/):
  zcn_sn_local_peak.csv     SN terminal local peaks + E2E (from sweep_sn_local_peak)
  zcn_sn_read_ceiling.csv   E2E read ceiling lambda sweep (optional)
  zcn_sn_write_ceiling.csv  E2E write ceiling lambda sweep (optional)

Outputs:
  zcn_sim_report.pdf
  zcn_sim_report_p1.png
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_CSV = os.path.join(HERE, os.environ.get("LOCAL_CSV", "zcn_sn_local_peak.csv"))
READ_CSV = os.path.join(HERE, os.environ.get("READ_CSV", "zcn_sn_read_ceiling.csv"))
WRITE_CSV = os.path.join(HERE, os.environ.get("WRITE_CSV", "zcn_sn_write_ceiling.csv"))
PDF_OUT = os.path.join(HERE, "zcn_sim_report.pdf")
PNG_OUT = os.path.join(HERE, "zcn_sim_report_p1.png")

VC_BUF = int(os.environ.get("ZCN_VC_BUF", "4"))
DATA_FLITS = int(os.environ.get("ZCN_DATA_FLITS", "2"))
FLIT_BYTES = 16

os.environ.setdefault("MPLCONFIGDIR", os.path.join(HERE, ".mplcache"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

COL_READ = "#2563eb"
COL_WRITE = "#dc2626"
COL_SN = "#059669"
COL_E2E = "#93c5fd"
COL_REQ = "#f59e0b"


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def load_sweep(path):
    rows = load_csv(path)
    out = []
    for r in rows:
        def num(k):
            v = r.get(k, "")
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        out.append({**r, "lambda": num("lambda"),
                    "read_util": num("read_util"),
                    "write_util": num("write_util")})
    out.sort(key=lambda x: x["lambda"] or 0)
    return out


def plateau(rows, key):
    best = None
    for r in rows:
        v = r.get(key)
        if v is None:
            continue
        if best is None or v > best[key]:
            best = {**r, key: v}
    return best


def main():
    local = load_csv(LOCAL_CSV)
    read_rows = load_sweep(READ_CSV)
    write_rows = load_sweep(WRITE_CSV)
    if not local:
        print(f"No data in {LOCAL_CSV}; run sweep first.")
        return

    read_local = next((r for r in local if r["mix"] == "read"), None)
    write_local = next((r for r in local if r["mix"] == "write"), None)
    read_e2e_plateau = plateau(read_rows, "read_util")
    write_e2e_plateau = plateau(write_rows, "write_util")

    with PdfPages(PDF_OUT) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle(
            "ZCN SN Read/Write Utilisation\n"
            f"vc_buf_size={VC_BUF} flits/VC, DATA_FLITS={DATA_FLITS}, "
            "XY routing, link_latency=2",
            fontsize=13, fontweight="bold", y=0.98,
        )

        # Page 1 top: bar chart SN local vs E2E
        ax = fig.add_axes([0.10, 0.58, 0.85, 0.32])
        cats = ["Read ceiling", "Write ceiling"]
        x = [0, 1]
        w = 0.22
        if read_local:
            ax.bar(x[0] - w, float(read_local["sn_dat_peak"]) * 100, w,
                   label="SN local DAT", color=COL_SN)
            ax.bar(x[0], float(read_local["e2e_dat_util"]) * 100, w,
                   label="E2E DAT util", color=COL_E2E)
            ax.bar(x[0] + w, float(read_local["sn_req_peak"]) * 100, w,
                   label="SN local REQ", color=COL_REQ)
        if write_local:
            ax.bar(x[1] - w, float(write_local["sn_dat_peak"]) * 100, w,
                   color=COL_SN)
            ax.bar(x[1], float(write_local["e2e_dat_util"]) * 100, w,
                   color=COL_E2E)
            ax.bar(x[1] + w, float(write_local["sn_req_peak"]) * 100, w,
                   color=COL_REQ)
        ax.axhline(100, color="#64748b", ls="--", lw=1, alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(cats)
        ax.set_ylabel("flit/cycle (% of 1.0 link)")
        ax.set_ylim(0, 110)
        ax.set_title("SN terminal peaks vs end-to-end DAT delivery (best λ per mix)")
        ax.legend(fontsize=8, loc="upper left", ncol=2)
        ax.grid(alpha=0.2, axis="y")

        # Lambda sweeps
        ax2 = fig.add_axes([0.10, 0.33, 0.85, 0.20])
        if read_rows:
            lam = [r["lambda"] for r in read_rows if r["read_util"] is not None]
            util = [r["read_util"] * 100 for r in read_rows if r["read_util"] is not None]
            ax2.plot(lam, util, "o-", color=COL_READ, label="Read E2E DAT util", ms=4)
        if write_rows:
            lam = [r["lambda"] for r in write_rows if r["write_util"] is not None]
            util = [r["write_util"] * 100 for r in write_rows if r["write_util"] is not None]
            ax2.plot(lam, util, "s-", color=COL_WRITE, label="Write E2E DAT util", ms=4)
        ax2.axhline(100, color="#64748b", ls="--", lw=1, alpha=0.5)
        ax2.set_xlabel("injection rate λ (txn/node/cycle)")
        ax2.set_ylabel("E2E DAT util (%)")
        ax2.set_title("E2E throughput vs offered load (read/write ceiling mixes)")
        ax2.legend(fontsize=8)
        ax2.grid(alpha=0.25)
        if not read_rows and not write_rows:
            ax2.text(0.5, 0.5, "No E2E sweep CSVs", ha="center", va="center",
                     transform=ax2.transAxes, color="#64748b")

        # Summary table
        axt = fig.add_axes([0.05, 0.08, 0.90, 0.20])
        axt.axis("off")
        header = ["Path", "λ*", "SN DAT peak", "SN DAT avg", "E2E DAT",
                  "SN REQ peak", "Gap (SN−E2E)", "State"]
        body = []
        for label, r in (("Read", read_local), ("Write", write_local)):
            if not r:
                continue
            sn = float(r["sn_dat_peak"])
            e2e = float(r["e2e_dat_util"])
            body.append([
                label, r["lambda"],
                f"{sn:.1%}", f"{float(r['sn_dat_avg']):.1%}",
                f"{e2e:.1%}", f"{float(r['sn_req_peak']):.1%}",
                f"{(sn - e2e):+.1%}", r["state"],
            ])
        tbl = axt.table(cellText=[header] + body, loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        tbl.scale(1.0, 1.6)
        for c in range(len(header)):
            tbl[0, c].set_facecolor("#1e293b")
            tbl[0, c].set_text_props(color="white", fontweight="bold")

        bw_flits = DATA_FLITS
        bw_b = bw_flits * FLIT_BYTES
        notes = (
            f"Config: 6×7 mesh CHI, 4 SN nodes (168–171), vc_buf={VC_BUF} flits/VC, "
            f"2 VCs, DATA_FLITS={DATA_FLITS} ({bw_b}B/packet on wire).\n"
            "Read ceiling: 100% ReadShared DMT miss → CompData SN→RN.  "
            "Write ceiling: 100% WriteBack + L3EvictToSN.\n"
            "SN local DAT read = max sent_flits@SN (inject); write = max accepted_flits@SN (eject).  "
            "E2E DAT = sweep_sn_throughput accepted-rate metric.\n"
            "Gap>0 on read ⇒ mesh fan-out limits delivery below SN inject capacity.  "
            "Gap≈0 on write ⇒ SN terminal link is the bottleneck."
        )
        if read_local and write_local:
            rd, wr = float(read_local["sn_dat_peak"]), float(write_local["sn_dat_peak"])
            notes += f"\nWrite/read SN DAT peak ratio: {wr/rd:.2f}× ({wr:.0%} vs {rd:.0%})."
        fig.text(0.05, 0.02, notes, fontsize=7.5, va="bottom",
                 bbox=dict(boxstyle="round", fc="#f8fafc", ec="#cbd5e1"))

        fig.savefig(PNG_OUT, dpi=120, bbox_inches="tight")
        pdf.savefig(fig)
        plt.close(fig)

    print(f"Wrote {PDF_OUT}")
    print(f"Wrote {PNG_OUT}")


if __name__ == "__main__":
    main()
