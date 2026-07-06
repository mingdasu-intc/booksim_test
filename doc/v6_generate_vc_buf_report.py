#!/usr/bin/env python3
"""Plot the vc_buf_size sensitivity of the SN read/write throughput ceiling.

Input : v6_repair_vc_buf_sweep.csv  (override via SWEEP_CSV)
Output: v6_repair_vc_buf_report.pdf + v6_repair_vc_buf_p1.png
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_IN = os.path.join(HERE, os.environ.get("SWEEP_CSV", "v6_repair_vc_buf_sweep.csv"))
PDF_OUT = os.path.join(HERE, "v6_repair_vc_buf_report.pdf")
PNG_OUT = os.path.join(HERE, "v6_repair_vc_buf_p1.png")

os.environ.setdefault("MPLCONFIGDIR", os.path.join(HERE, ".mplcache"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

COL_READ = "#2563eb"
COL_WRITE = "#dc2626"
COL_CEIL = "#64748b"


def load():
    rows = []
    with open(CSV_IN) as f:
        for r in csv.DictReader(f):
            rows.append({
                "buf": int(r["vc_buf_size"]),
                "rd_per_sn": float(r["read_per_sn"]),
                "rd_util": float(r["read_util"]),
                "wr_per_sn": float(r["write_per_sn"]),
                "wr_util": float(r["write_util"]),
            })
    rows.sort(key=lambda x: x["buf"])
    return rows


def main():
    rows = load()
    bufs = [r["buf"] for r in rows]
    rd = [r["rd_util"] for r in rows]
    wr = [r["wr_util"] for r in rows]

    with PdfPages(PDF_OUT) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("SN Throughput Ceiling vs VC Buffer Depth\n"
                     "6x7 mesh + 4 SN, XY routing, 2-cycle links, 2 VCs",
                     fontsize=14, fontweight="bold", y=0.975)

        ax = fig.add_axes([0.12, 0.56, 0.80, 0.33])
        ax.plot(bufs, [x * 100 for x in wr], "-o", color=COL_WRITE, label="write ceiling (HN->SN)")
        ax.plot(bufs, [x * 100 for x in rd], "-o", color=COL_READ, label="read ceiling (SN->RN)")
        ax.axhline(100, color=COL_CEIL, ls="--", lw=1.2)
        ax.text(bufs[0], 101, " structural link limit = 100%", color="#475569", fontsize=8)
        ax.set_xscale("log", base=2)
        ax.set_xticks(bufs)
        ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax.set_xlabel("vc_buf_size (flits per VC)")
        ax.set_ylabel("Per-SN link utilisation (%)")
        ax.set_title("Achievable per-SN utilisation vs buffer depth")
        ax.set_ylim(0, 108)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=9, loc="lower right")
        for r in rows:
            ax.annotate(f"{r['wr_util']*100:.0f}%", (r["buf"], r["wr_util"]*100),
                        textcoords="offset points", xytext=(0, 6), ha="center", fontsize=7, color=COL_WRITE)
            ax.annotate(f"{r['rd_util']*100:.0f}%", (r["buf"], r["rd_util"]*100),
                        textcoords="offset points", xytext=(0, -12), ha="center", fontsize=7, color=COL_READ)

        # table
        axt = fig.add_axes([0.10, 0.30, 0.80, 0.18])
        axt.axis("off")
        header = ["vc_buf", "read /SN\n(flit/cyc)", "read util", "write /SN\n(flit/cyc)", "write util"]
        body = [[str(r["buf"]), f"{r['rd_per_sn']:.3f}", f"{r['rd_util']:.1%}",
                 f"{r['wr_per_sn']:.3f}", f"{r['wr_util']:.1%}"] for r in rows]
        table = axt.table(cellText=[header] + body, loc="center", cellLoc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.0, 1.8)
        for c in range(len(header)):
            table[0, c].set_facecolor("#1e293b")
            table[0, c].set_text_props(color="white", fontweight="bold")

        notes = (
            "Reading the curve:\n"
            "- buffer 2->4 flits gives the biggest jump (read 33%->62%, write 53%->88%): the 2-flit VC buffer "
            "could not cover the link credit round-trip (2-cycle links), so the link idled waiting for credits. "
            "Deepening the buffer removes that stall.\n"
            "- Write saturates near ~91% at buf>=8: the HN->SN data path becomes essentially link-bound.\n"
            "- Read plateaus at ~70% even with deep buffers: the residual gap is NOT the buffer but the 84 HN -> 4 SN "
            "fan-in plus the read request round-trip (REQ into SN throttles the DMT data out). Buffer depth cannot "
            "fix a topological fan-in limit.\n"
            "- Diminishing returns past buf=8: buffer is no longer the bottleneck.\n\n"
            "Takeaway: vc_buf_size=8 captures almost all of the benefit; write becomes link-bound, read becomes "
            "fan-in/round-trip-bound. To push read further, add/spread SN nodes or shorten the coherence round-trip."
        )
        fig.text(0.10, 0.25, notes, fontsize=9, va="top", wrap=True,
                 bbox=dict(boxstyle="round", fc="#f8fafc", ec="#cbd5e1"))
        fig.text(0.5, 0.03, "Ceiling = max sustained per-SN accepted data across the offered-load sweep, all traffic "
                            "forced to the 4 SNs.", ha="center", fontsize=8, color="#475569")
        fig.savefig(PNG_OUT, dpi=120)
        pdf.savefig(fig)
        plt.close(fig)

    print(f"Wrote {PDF_OUT}")
    print(f"Wrote {PNG_OUT}")


if __name__ == "__main__":
    main()
