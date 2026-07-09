#!/usr/bin/env python3
"""Compare SN ceiling vs vc_buf_size for CHI_DATA_FLITS = 1, 2, 4.

Inputs (doc/):
  CSV_D2  v6_repair_vc_buf_sweep.csv           (DATA_FLITS=2, default)
  CSV_D1  v6_repair_DATAFLIT1_vc_buf_sweep.csv (DATA_FLITS=1)
  CSV_D4  v6_repair_DATAFLIT4_vc_buf_sweep.csv (DATA_FLITS=4)

Output:
  v6_repair_DATAFLIT1_report.pdf   (shared report name, all D values)
  v6_repair_DATAFLIT1_p1.png
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_D2 = os.path.join(HERE, os.environ.get("CSV_D2", "v6_repair_vc_buf_sweep.csv"))
CSV_D1 = os.path.join(HERE, os.environ.get("CSV_D1", "v6_repair_DATAFLIT1_vc_buf_sweep.csv"))
CSV_D4 = os.path.join(HERE, os.environ.get("CSV_D4", "v6_repair_DATAFLIT4_vc_buf_sweep.csv"))
PDF_OUT = os.path.join(HERE, "v6_repair_DATAFLIT1_report.pdf")
PNG_OUT = os.path.join(HERE, "v6_repair_DATAFLIT1_p1.png")

FLIT_BYTES = 16

os.environ.setdefault("MPLCONFIGDIR", os.path.join(HERE, ".mplcache"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

SERIES = [
    ("D=2", CSV_D2, "-o", {"write": "#dc2626", "read": "#2563eb"}),
    ("D=1", CSV_D1, "--s", {"write": "#f87171", "read": "#60a5fa"}),
    ("D=4", CSV_D4, "-.^", {"write": "#991b1b", "read": "#1e40af"}),
]


def load(path):
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append({
                "buf": int(r["vc_buf_size"]),
                "rd": float(r["read_util"]),
                "wr": float(r["write_util"]),
                "rd_sn": float(r["read_per_sn"]),
                "wr_sn": float(r["write_per_sn"]),
            })
    rows.sort(key=lambda x: x["buf"])
    return rows


def gap(rows):
    return [(r["wr"] - r["rd"]) * 100 for r in rows]


def main():
    data = [(label, load(path)) for label, path, _, _ in SERIES]
    bufs = data[0][1] and [r["buf"] for r in data[0][1]] or []

    with PdfPages(PDF_OUT) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("SN Ceiling: DATA_FLITS = 1 / 2 / 4\n"
                     "6x7 mesh + 4 SN, XY, 2-cycle links, 2 VCs",
                     fontsize=14, fontweight="bold", y=0.975)

        ax1 = fig.add_axes([0.12, 0.58, 0.80, 0.30])
        for (label, rows), (_, _, ls, colors) in zip(data, SERIES):
            ax1.plot(bufs, [r["wr"]*100 for r in rows], ls, color=colors["write"],
                     label=f"write {label}", markersize=5)
            ax1.plot(bufs, [r["rd"]*100 for r in rows], ls, color=colors["read"],
                     label=f"read {label}", markersize=5)
        ax1.axhline(100, color="#64748b", ls=":", lw=1)
        ax1.set_xscale("log", base=2)
        ax1.set_xticks(bufs)
        ax1.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax1.set_xlabel("vc_buf_size (flits / VC)")
        ax1.set_ylabel("Per-SN link utilisation (%)")
        ax1.set_title("Read / write ceiling utilisation (flit/cycle)")
        ax1.set_ylim(0, 108)
        ax1.grid(alpha=0.25)
        ax1.legend(fontsize=7, ncol=3, loc="lower right")

        ax2 = fig.add_axes([0.12, 0.30, 0.80, 0.22])
        w = 0.22
        offsets = [-w, 0, w]
        gap_colors = ["#94a3b8", "#475569", "#334155"]
        for i, ((label, rows), off, col) in enumerate(zip(data, offsets, gap_colors)):
            ax2.bar([b + off for b in bufs], gap(rows), width=w,
                    label=f"gap {label}", color=col, alpha=0.85)
        ax2.set_xscale("log", base=2)
        ax2.set_xticks(bufs)
        ax2.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax2.set_xlabel("vc_buf_size")
        ax2.set_ylabel("write - read util (pp)")
        ax2.set_title("Read/write gap (percentage points)")
        ax2.legend(fontsize=8)
        ax2.grid(alpha=0.25, axis="y")

        axt = fig.add_axes([0.04, 0.06, 0.92, 0.18])
        axt.axis("off")
        header = ["vc_buf"]
        for label, _, _, _ in SERIES:
            header += [f"rd {label}", f"wr {label}", "gap"]
        body = []
        for i, b in enumerate(bufs):
            row = [str(b)]
            for _, rows in data:
                r = rows[i]
                row += [f"{r['rd']*100:.1f}%", f"{r['wr']*100:.1f}%",
                        f"{(r['wr']-r['rd'])*100:.1f}"]
            body.append(row)
        tbl = axt.table(cellText=[header] + body, loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(7)
        tbl.scale(1.0, 1.5)
        for c in range(len(header)):
            tbl[0, c].set_facecolor("#1e293b")
            tbl[0, c].set_text_props(color="white", fontweight="bold")

        notes = (
            f"DAT packet = D flits x {FLIT_BYTES} B/flit. Utilisation is flit/cycle on the SN "
            "terminal link (1 flit/cycle structural max). Larger D packs more flits per txn on "
            "the DAT link, so read util in flit/cycle can rise with D even when txn rate is "
            "REQ-limited. D=4 improves both ceilings at buf>=4; read/write gap narrows slightly "
            "vs D=2 but write still leads due to REQ fan-in on the read path."
        )
        fig.text(0.5, 0.01, notes, ha="center", fontsize=7.5, color="#475569", wrap=True)
        fig.savefig(PNG_OUT, dpi=120)
        pdf.savefig(fig)
        plt.close(fig)

    print(f"Wrote {PDF_OUT}")
    print(f"Wrote {PNG_OUT}")
    for i, b in enumerate(bufs):
        parts = [f"buf={b:2d}"]
        for label, rows in data:
            r = rows[i]
            parts.append(f"{label} rd={r['rd']*100:.0f}% wr={r['wr']*100:.0f}% "
                         f"gap={(r['wr']-r['rd'])*100:.0f}pp")
        print("  " + " | ".join(parts))


if __name__ == "__main__":
    main()
