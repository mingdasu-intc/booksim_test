#!/usr/bin/env python3
"""ZCN scenario report: vc_buf=4, DATA_FLITS=2, SN read/write utilization.

Inputs (doc/):
  zcn_sn_local_peak.csv       SN terminal metrics at λ* (max SN DAT avg per mix)
  zcn_sn_local_peak_sweep.csv full λ sweep — SN DAT avg vs λ curve

Outputs:
  zcn_sim_report.pdf
  zcn_sim_report_p1.png
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_CSV = os.path.join(HERE, os.environ.get("LOCAL_CSV", "zcn_sn_local_peak.csv"))
SWEEP_CSV = os.path.join(HERE, os.environ.get("SWEEP_CSV", "zcn_sn_local_peak_sweep.csv"))
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
COL_REQ = "#f59e0b"


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def load_sweep(path):
    rows = []
    for r in load_csv(path):
        try:
            lam = float(r["lambda"])
            avg = float(r["sn_dat_avg"])
        except (TypeError, ValueError, KeyError):
            continue
        rows.append({**r, "lambda": lam, "sn_dat_avg": avg})
    rows.sort(key=lambda x: (x.get("mix", ""), x["lambda"]))
    return rows


def best_by_avg(rows, mix):
    """Return the sweep row with highest sn_dat_avg for a mix."""
    pts = [r for r in rows if r.get("mix") == mix]
    if not pts:
        return None
    return max(pts, key=lambda r: r["sn_dat_avg"])


def main():
    local = load_csv(LOCAL_CSV)
    sweep = load_sweep(SWEEP_CSV)
    if sweep:
        read_local = best_by_avg(sweep, "read")
        write_local = best_by_avg(sweep, "write")
    elif local:
        read_local = next((r for r in local if r["mix"] == "read"), None)
        write_local = next((r for r in local if r["mix"] == "write"), None)
    else:
        print(f"No data in {SWEEP_CSV} or {LOCAL_CSV}; run sweep first.")
        return

    read_sweep = [r for r in sweep if r.get("mix") == "read"]
    write_sweep = [r for r in sweep if r.get("mix") == "write"]

    with PdfPages(PDF_OUT) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle(
            "ZCN SN Read/Write Utilisation\n"
            f"vc_buf_size={VC_BUF} flits/VC, DATA_FLITS={DATA_FLITS}, "
            "XY routing, link_latency=2",
            fontsize=13, fontweight="bold", y=0.98,
        )

        # Bar chart: SN local DAT + REQ peaks
        ax = fig.add_axes([0.10, 0.58, 0.85, 0.30])
        cats = ["Read ceiling", "Write ceiling"]
        x = [0, 1]
        w = 0.28
        if read_local:
            ax.bar(x[0] - w / 2, float(read_local["sn_dat_peak"]) * 100, w,
                   label="SN local DAT peak", color=COL_SN)
            ax.bar(x[0] + w / 2, float(read_local["sn_req_peak"]) * 100, w,
                   label="SN local REQ peak", color=COL_REQ)
        if write_local:
            ax.bar(x[1] - w / 2, float(write_local["sn_dat_peak"]) * 100, w,
                   color=COL_SN)
            ax.bar(x[1] + w / 2, float(write_local["sn_req_peak"]) * 100, w,
                   color=COL_REQ)
        ax.axhline(100, color="#64748b", ls="--", lw=1, alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(cats)
        ax.set_ylabel("flit/cycle (% of 1.0 link)")
        ax.set_ylim(0, 110)
        ax.set_title("SN terminal peaks at λ* (max SN DAT avg per mix)")
        ax.legend(fontsize=9, loc="upper left")
        ax.grid(alpha=0.2, axis="y")

        # SN DAT average vs lambda
        ax2 = fig.add_axes([0.10, 0.33, 0.85, 0.20])
        if read_sweep:
            ax2.plot(
                [r["lambda"] for r in read_sweep],
                [r["sn_dat_avg"] * 100 for r in read_sweep],
                "o-", color=COL_READ, label="Read SN DAT avg", ms=4, lw=1.5,
            )
        if write_sweep:
            ax2.plot(
                [r["lambda"] for r in write_sweep],
                [r["sn_dat_avg"] * 100 for r in write_sweep],
                "s-", color=COL_WRITE, label="Write SN DAT avg", ms=4, lw=1.5,
            )
        for label, r, col in (
            ("Read λ*", read_local, COL_READ),
            ("Write λ*", write_local, COL_WRITE),
        ):
            if not r:
                continue
            lam = float(r["lambda"])
            avg = float(r["sn_dat_avg"]) * 100
            ax2.axvline(lam, color=col, ls=":", lw=1.2, alpha=0.75)
            ax2.plot(lam, avg, "*", color=col, ms=12, zorder=5,
                     label=f"{label}={lam:g} ({avg:.1f}%)")
        ax2.axhline(100, color="#64748b", ls="--", lw=1, alpha=0.5)
        ax2.set_xlabel("injection rate λ (txn/node/cycle)")
        ax2.set_ylabel("SN DAT avg (%)")
        ax2.set_title("SN DAT average vs offered load")
        ax2.legend(fontsize=8)
        ax2.grid(alpha=0.25)
        if not read_sweep and not write_sweep:
            ax2.text(0.5, 0.5, f"No sweep data in {os.path.basename(SWEEP_CSV)}",
                     ha="center", va="center", transform=ax2.transAxes, color="#64748b")

        # Summary table
        axt = fig.add_axes([0.08, 0.10, 0.84, 0.18])
        axt.axis("off")
        header = ["Path", "λ* (max avg)", "SN DAT peak", "SN DAT avg",
                  "SN REQ peak", "SN REQ avg", "State"]
        body = []
        for label, r in (("Read", read_local), ("Write", write_local)):
            if not r:
                continue
            body.append([
                label, r["lambda"],
                f"{float(r['sn_dat_peak']):.1%}",
                f"{float(r['sn_dat_avg']):.1%}",
                f"{float(r['sn_req_peak']):.1%}",
                f"{float(r['sn_req_avg']):.1%}",
                r["state"],
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
            "SN local REQ = max accepted_flits@SN on REQ channel to SN.  "
            "λ* = injection rate with highest SN DAT avg across the sweep."
        )
        if read_local and write_local:
            rd_avg = float(read_local["sn_dat_avg"])
            wr_avg = float(write_local["sn_dat_avg"])
            notes += (
                f"\nWrite/read SN DAT avg ratio at λ*: {wr_avg/rd_avg:.2f}× "
                f"({wr_avg:.0%} vs {rd_avg:.0%})."
            )
        fig.text(0.05, 0.02, notes, fontsize=7.5, va="bottom",
                 bbox=dict(boxstyle="round", fc="#f8fafc", ec="#cbd5e1"))

        fig.savefig(PNG_OUT, dpi=120, bbox_inches="tight")
        pdf.savefig(fig)
        plt.close(fig)

    print(f"Wrote {PDF_OUT}")
    print(f"Wrote {PNG_OUT}")


if __name__ == "__main__":
    main()
