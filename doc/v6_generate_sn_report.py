#!/usr/bin/env python3
"""Build the SN (DDR) read/write throughput report from sweep_sn_throughput CSVs.

Inputs (in this doc/ folder, override via env):
  CURRENT_CSV  v6_sn_throughput_current.csv   (current traffic mix)
  READ_CSV     v6_sn_read_ceiling.csv         (read-focused mix, dmt_miss=100%)
  WRITE_CSV    v6_sn_write_ceiling.csv        (write-focused mix, L3EvictToSN=100%)

Output:
  v6_sn_throughput_report.pdf
  v6_sn_throughput_p1.png  (preview of page 1)

Throughput is reported in flit/cycle. The structural ceiling of one SN terminal
link is 1 flit/cycle (full-duplex, no speedup), i.e. 4 flit/cycle aggregated over
the 4 SNs. flit = 16 bytes (FLIT_BYTES in gen_chi_traffic.py) for the optional
byte-bandwidth reference.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CURRENT_CSV = os.path.join(HERE, os.environ.get("CURRENT_CSV", "v6_sn_throughput_current.csv"))
READ_CSV = os.path.join(HERE, os.environ.get("READ_CSV", "v6_sn_read_ceiling.csv"))
WRITE_CSV = os.path.join(HERE, os.environ.get("WRITE_CSV", "v6_sn_write_ceiling.csv"))
PDF_OUT = os.path.join(HERE, os.environ.get("REPORT_PDF", "v6_sn_throughput_report.pdf"))
PNG_OUT = os.path.join(HERE, os.environ.get("REPORT_PNG", "v6_sn_throughput_p1.png"))

LINK_CEILING = 1.0     # flit/cycle per SN terminal link
FLIT_BYTES = 16

os.environ.setdefault("MPLCONFIGDIR", os.path.join(HERE, ".mplcache"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

COL_READ = "#2563eb"
COL_WRITE = "#dc2626"
COL_CEIL = "#64748b"


def load(path):
    if not os.path.exists(path):
        return None
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            def num(k):
                v = r.get(k, "")
                return float(v) if v not in ("", "None", None) else None
            rows.append({
                "lambda": num("lambda"),
                "state": r.get("state", ""),
                "n_sn": num("n_sn"),
                "read_acc_per_sn": num("read_acc_per_sn"),
                "read_acc_total": num("read_acc_total"),
                "read_inj_per_sn": num("read_inj_per_sn"),
                "read_util": num("read_util"),
                "read_flat": num("read_flat"),
                "write_acc_per_sn": num("write_acc_per_sn"),
                "write_acc_total": num("write_acc_total"),
                "write_inj_per_sn": num("write_inj_per_sn"),
                "write_util": num("write_util"),
                "write_flat": num("write_flat"),
            })
    rows.sort(key=lambda x: (x["lambda"] if x["lambda"] is not None else 0))
    return rows


def plateau(rows, key):
    """Max sustained per-SN throughput and the row where it occurs."""
    best = None
    for r in rows or []:
        v = r.get(key)
        if v is None:
            continue
        if best is None or v > best[key]:
            best = r
    return best


def split_state(rows, xkey, ykey):
    st = [(r[xkey], r[ykey]) for r in rows
          if r.get(ykey) is not None and r["state"] == "ok"]
    un = [(r[xkey], r[ykey]) for r in rows
          if r.get(ykey) is not None and r["state"] != "ok"]
    return st, un


def draw_curve(ax, rows, xkey, ykey, color, label):
    st, un = split_state(rows, xkey, ykey)
    if st:
        xs, ys = zip(*st)
        ax.plot(xs, ys, "-o", color=color, label=label, markersize=4)
    if un:
        bridge = ([st[-1]] if st else []) + un
        bx, by = zip(*bridge)
        ax.plot(bx, by, "--x", color=color, markersize=7, lw=1.2,
                label=f"{label} (unstable)")


def fmt(x, d=4):
    return "-" if x is None else f"{x:.{d}f}"


def main():
    current = load(CURRENT_CSV)
    readc = load(READ_CSV)
    writec = load(WRITE_CSV)

    rd_ceil = plateau(readc, "read_acc_per_sn") if readc else None
    wr_ceil = plateau(writec, "write_acc_per_sn") if writec else None

    with PdfPages(PDF_OUT) as pdf:
        # ---- page 1: current traffic operating point ----
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("SN (DDR) Throughput - Current Traffic Mix\n"
                     "6x7 mesh + 4 SN, XY routing, 2-cycle links",
                     fontsize=14, fontweight="bold", y=0.975)
        if current:
            ax1 = fig.add_axes([0.12, 0.58, 0.80, 0.31])
            draw_curve(ax1, current, "lambda", "read_acc_per_sn", COL_READ, "read data / SN")
            draw_curve(ax1, current, "lambda", "write_acc_per_sn", COL_WRITE, "write data / SN")
            ax1.axhline(LINK_CEILING, color=COL_CEIL, ls="--", lw=1.2)
            ax1.text(ax1.get_xlim()[0], LINK_CEILING * 1.02,
                     " structural ceiling = 1 flit/cycle/SN", color="#475569", fontsize=8)
            ax1.set_xlabel("Total transaction rate LAMBDA (txn / node / cycle)")
            ax1.set_ylabel("Per-SN accepted data (flit / cycle)")
            ax1.set_title("Per-SN read/write data throughput vs offered load")
            ax1.grid(alpha=0.25)
            ax1.legend(fontsize=9)

            ax2 = fig.add_axes([0.12, 0.16, 0.80, 0.30])
            draw_curve(ax2, current, "lambda", "read_util", COL_READ, "read link util")
            draw_curve(ax2, current, "lambda", "write_util", COL_WRITE, "write link util")
            ax2.set_xlabel("Total transaction rate LAMBDA")
            ax2.set_ylabel("SN link utilisation (of 1 flit/cycle)")
            ax2.set_title("SN terminal-link utilisation (current mix)")
            ax2.grid(alpha=0.25)
            ax2.legend(fontsize=9)
            last = current[-1]
            fig.text(0.12, 0.09,
                     f"At the network saturation point the SN links carry only "
                     f"~{(last['read_util'] or 0):.2%} (read) / ~{(last['write_util'] or 0):.2%} "
                     f"(write) of their 1 flit/cycle capacity: under the current mix the SN is far "
                     f"from being the bottleneck.",
                     fontsize=9, va="top", wrap=True,
                     bbox=dict(boxstyle="round", fc="#f8fafc", ec="#cbd5e1"))
        else:
            fig.text(0.5, 0.5, "current-mix CSV not found", ha="center")
        fig.savefig(PNG_OUT, dpi=120)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- page 2: read ceiling & write ceiling curves ----
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("SN Read / Write Throughput Ceiling (focused mixes)",
                     fontsize=14, fontweight="bold", y=0.975)

        ax3 = fig.add_axes([0.12, 0.58, 0.80, 0.31])
        if readc:
            draw_curve(ax3, readc, "lambda", "read_acc_per_sn", COL_READ, "read data / SN")
            ax3.axhline(LINK_CEILING, color=COL_CEIL, ls="--", lw=1.2)
            if rd_ceil:
                ax3.axhline(rd_ceil["read_acc_per_sn"], color=COL_READ, ls=":", lw=1.0)
                ax3.text(ax3.get_xlim()[0], rd_ceil["read_acc_per_sn"] * 1.02,
                         f" plateau = {rd_ceil['read_acc_per_sn']:.3f} flit/cyc/SN",
                         color=COL_READ, fontsize=8)
        else:
            ax3.text(0.5, 0.5, "read-ceiling CSV not found", ha="center", transform=ax3.transAxes)
        ax3.set_xlabel("Total transaction rate LAMBDA")
        ax3.set_ylabel("Per-SN read data (flit / cycle)")
        ax3.set_title("Read ceiling: dmt_miss=100% (all read data from SN)")
        ax3.grid(alpha=0.25)
        ax3.legend(fontsize=9)

        ax4 = fig.add_axes([0.12, 0.16, 0.80, 0.30])
        if writec:
            draw_curve(ax4, writec, "lambda", "write_acc_per_sn", COL_WRITE, "write data / SN")
            ax4.axhline(LINK_CEILING, color=COL_CEIL, ls="--", lw=1.2)
            if wr_ceil:
                ax4.axhline(wr_ceil["write_acc_per_sn"], color=COL_WRITE, ls=":", lw=1.0)
                ax4.text(ax4.get_xlim()[0], wr_ceil["write_acc_per_sn"] * 1.02,
                         f" plateau = {wr_ceil['write_acc_per_sn']:.3f} flit/cyc/SN",
                         color=COL_WRITE, fontsize=8)
        else:
            ax4.text(0.5, 0.5, "write-ceiling CSV not found", ha="center", transform=ax4.transAxes)
        ax4.set_xlabel("Total transaction rate LAMBDA")
        ax4.set_ylabel("Per-SN write data (flit / cycle)")
        ax4.set_title("Write ceiling: WriteBack + L3EvictToSN=100% (all write data to SN)")
        ax4.grid(alpha=0.25)
        ax4.legend(fontsize=9)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- page 3: summary table + notes ----
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("SN Throughput Ceiling - Summary", fontsize=14,
                     fontweight="bold", y=0.975)
        ax = fig.add_axes([0.06, 0.62, 0.88, 0.28])
        ax.axis("off")

        def bw_bytes(flit_per_cyc):
            return "-" if flit_per_cyc is None else f"{flit_per_cyc * FLIT_BYTES:.2f} B/cyc"

        header = ["Metric", "per SN\n(flit/cyc)", "4-SN total\n(flit/cyc)",
                  "util vs\n1 flit/cyc", "per-SN\nbytes/cyc"]
        table_rows = []
        if rd_ceil:
            table_rows.append([
                "Read ceiling (SN->RN)",
                fmt(rd_ceil["read_acc_per_sn"], 3),
                fmt(rd_ceil["read_acc_total"], 3),
                f"{(rd_ceil['read_util'] or 0):.1%}",
                bw_bytes(rd_ceil["read_acc_per_sn"]),
            ])
        if wr_ceil:
            table_rows.append([
                "Write ceiling (HN->SN)",
                fmt(wr_ceil["write_acc_per_sn"], 3),
                fmt(wr_ceil["write_acc_total"], 3),
                f"{(wr_ceil['write_util'] or 0):.1%}",
                bw_bytes(wr_ceil["write_acc_per_sn"]),
            ])
        if current:
            last = current[-1]
            table_rows.append([
                "Read @ current mix (sat.)",
                fmt(last["read_acc_per_sn"], 4),
                fmt(last["read_acc_total"], 4),
                f"{(last['read_util'] or 0):.2%}",
                bw_bytes(last["read_acc_per_sn"]),
            ])
            table_rows.append([
                "Write @ current mix (sat.)",
                fmt(last["write_acc_per_sn"], 4),
                fmt(last["write_acc_total"], 4),
                f"{(last['write_util'] or 0):.2%}",
                bw_bytes(last["write_acc_per_sn"]),
            ])
        if not table_rows:
            table_rows = [["no data", "-", "-", "-", "-"]]
        table = ax.table(cellText=[header] + table_rows, loc="center", cellLoc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(8.5)
        table.scale(1.0, 2.0)
        for col in range(len(header)):
            table[0, col].set_facecolor("#1e293b")
            table[0, col].set_text_props(color="white", fontweight="bold")

        notes = [
            "Structural ceiling: each SN attaches to its router with one full-duplex terminal link = 1 flit/cycle "
            "per direction (channel_width is power-only; no crossbar speedup). Read data (SN->RN) and write data "
            "(HN->SN) use separate links, each capped at 1 flit/cycle/SN -> 4 flit/cycle aggregated over the 4 SNs.",
            "Read ceiling: with dmt_miss=100% all read data is served by the 4 SNs; each SN injects CompData_DMT "
            "(2-flit) on the DAT subnet. As LAMBDA rises the SN DAT inject link is the binding constraint and the "
            "per-SN read throughput plateaus (unstable points captured from the last periodic snapshot).",
            "Write ceiling: with WriteBack + L3EvictToSN=100% all writeback data lands on the 4 SNs; each SN ejects "
            "L3EvictData (2-flit) on DAT, plateauing at its ejection-link limit.",
            "Gap vs 1 flit/cycle reflects the router microarchitecture: 2 VCs/input, 2-flit VC buffers, single "
            "alloc iteration, output-first round-robin, and 2-cycle inter-router links (deeper VC buffers raise the "
            "achievable fraction).",
            "Under the current mix the SN links sit at <1% utilisation even at network saturation, so the SN is not "
            "today's bottleneck; the ceiling above is what a memory-bound workload could extract from this topology.",
        ]
        fig.text(0.06, 0.52, "\n\n".join(f"- {n}" for n in notes),
                 fontsize=9, va="top", wrap=True,
                 bbox=dict(boxstyle="round", fc="#f8fafc", ec="#cbd5e1"))
        fig.text(0.5, 0.04,
                 "flit = 16 B; per-SN bytes/cyc = flit/cyc x 16. Ceilings measured with focused traffic mixes "
                 "on the persisted baseline (XY routing, 2-cycle links).",
                 ha="center", fontsize=8, color="#475569")
        pdf.savefig(fig)
        plt.close(fig)

    print(f"Wrote {PDF_OUT}")
    print(f"Wrote {PNG_OUT}")
    if rd_ceil:
        print(f"Read  ceiling: {rd_ceil['read_acc_per_sn']:.3f} flit/cyc/SN "
              f"({rd_ceil['read_acc_total']:.3f} total, util {rd_ceil['read_util']:.1%}) "
              f"@ LAMBDA={rd_ceil['lambda']}")
    if wr_ceil:
        print(f"Write ceiling: {wr_ceil['write_acc_per_sn']:.3f} flit/cyc/SN "
              f"({wr_ceil['write_acc_total']:.3f} total, util {wr_ceil['write_util']:.1%}) "
              f"@ LAMBDA={wr_ceil['lambda']}")


if __name__ == "__main__":
    main()
