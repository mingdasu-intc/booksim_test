#!/usr/bin/env python3
"""Render the V2 (class_subnet) CHI mesh sweep into a PDF chart report.

Reads runfiles/chi_v2_sweep_results.csv -> doc/v3_mesh6x7_chi_v2_report.pdf (+ p1 PNG).
Highlights that the shared DAT subnet (read-data + write-data) is the bottleneck.
"""
import os, csv

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("MPLCONFIGDIR", os.path.join(HERE, ".mplcache"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

CSV = os.path.join(HERE, "..", "runfiles", "chi_v2_sweep_results.csv")
OUT = os.path.join(HERE, "v3_mesh6x7_chi_v2_report.pdf")

CH = [("REQ", "#2563eb", "o", "-"),
      ("DAT_rd", "#dc2626", "s", "-"),
      ("SNP", "#16a34a", "^", "-"),
      ("RSP", "#7c3aed", "D", "-"),
      ("DAT_wr", "#ea580c", "v", "--")]

off, lat = [], {c[0]: [] for c in CH}
sat_x = None
with open(CSV) as f:
    for row in csv.DictReader(f):
        if row["state"] == "SAT":
            sat_x = float(row["offered"]); continue
        off.append(float(row["offered"]))
        for name, *_ in CH:
            v = row[f"{name}_lat"]
            lat[name].append(float(v) if v else None)
knee_x = off[-1]

with PdfPages(OUT) as pdf:
    # ---------- Page 1: latency vs offered ----------
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.suptitle("6x7 Mesh + CHI V2 (class_subnet patch)\n"
                 "Per-Channel Latency vs. Offered Load",
                 fontsize=15, fontweight="bold", y=0.97)

    ax = fig.add_axes([0.12, 0.40, 0.78, 0.46])
    for name, color, mk, ls in CH:
        ax.plot(off, lat[name], mk + ls, color=color, label=name, lw=1.8, ms=6)
    if sat_x is not None:
        ax.axvline(sat_x, color="gray", ls=":", lw=1.2)
        ax.text(sat_x, ax.get_ylim()[1]*0.55, f" saturation\n @ {sat_x}",
                color="gray", fontsize=9, va="center")
    ax.set_xlabel("Offered load (base request rate / node)")
    ax.set_ylabel("Average packet latency (cycles)")
    ax.grid(True, alpha=0.3)
    ax.legend(title="CHI channel")

    note = ("Key finding: the control channels (REQ / SNP / RSP, 1-flit) stay flat "
            "at ~34 cycles,\nwhile the two 5-flit DATA flows (DAT_rd HN->RN and "
            "DAT_wr RN->RN) share the\nsingle DAT subnet and climb steeply -- the "
            "DAT physical channel saturates first\n(knee ~ %.4f, unstable at %s). "
            "This mirrors real CHI, where DAT bandwidth\nis the system bottleneck."
            % (knee_x, sat_x))
    fig.text(0.12, 0.13, note, fontsize=10, va="top", color="#222",
             bbox=dict(boxstyle="round", fc="#fff7ed", ec="#ea580c"))
    fig.text(0.5, 0.04,
             "168 nodes (84 RN + 84 HN) | subnets=4 | 5 classes via class_subnet={0,1,2,3,1} | "
             "snoop=1.0, write_fraction=0.3",
             ha="center", fontsize=8.5, color="#444")
    fig.savefig(os.path.join(HERE, "v3_mesh6x7_chi_v2_report_p1.png"), dpi=110)
    pdf.savefig(fig); plt.close(fig)

    # ---------- Page 2: channel map + data table ----------
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.suptitle("V2 Channel Mapping & Sweep Data", fontsize=15,
                 fontweight="bold", y=0.97)

    ax2 = fig.add_axes([0.06, 0.60, 0.88, 0.28]); ax2.axis("off")
    mp = [["class", "CHI channel", "subnet", "size", "direction"],
          ["c0", "REQ", "0", "1", "RN->HN"],
          ["c1", "DAT (read)", "1", "5", "HN->RN"],
          ["c2", "SNP", "2", "1", "->RN"],
          ["c3", "RSP", "3", "1", "->HN"],
          ["c4", "DAT (write)", "1", "5", "RN->HN  (NEW vs V1)"]]
    t1 = ax2.table(cellText=mp, loc="center", cellLoc="center")
    t1.auto_set_font_size(False); t1.set_fontsize(10); t1.scale(1, 1.6)
    for c in range(5):
        t1[0, c].set_facecolor("#1e293b"); t1[0, c].set_text_props(color="white", fontweight="bold")
    for c in range(5):  # highlight the two DAT rows sharing subnet 1
        t1[2, c].set_facecolor("#fee2e2"); t1[5, c].set_facecolor("#ffedd5")
    ax2.set_title("4 channels = 4 subnets; DAT subnet shared by read+write data",
                  fontsize=12, pad=12)

    ax3 = fig.add_axes([0.04, 0.10, 0.92, 0.42]); ax3.axis("off")
    hdr = ["offered"] + [name for name, *_ in CH]
    data = [[f"{off[i]}"] + [f"{lat[n][i]:.1f}" if lat[n][i] else "-"
                             for n, *_ in CH] for i in range(len(off))]
    if sat_x is not None:
        data.append([f"{sat_x}"] + ["SAT"] * len(CH))
    t2 = ax3.table(cellText=[hdr] + data, loc="center", cellLoc="center")
    t2.auto_set_font_size(False); t2.set_fontsize(10); t2.scale(1, 1.5)
    for c in range(len(hdr)):
        t2[0, c].set_facecolor("#1e293b"); t2[0, c].set_text_props(color="white", fontweight="bold")
    for c in range(len(hdr)):  # knee row
        t2[len(off), c].set_facecolor("#fde68a")
    ax3.set_title("Per-channel average packet latency (cycles)", fontsize=12, pad=12)
    fig.text(0.5, 0.05, "Highlighted row = last stable point (knee). DAT columns drive saturation.",
             ha="center", fontsize=9, color="#444")
    pdf.savefig(fig); plt.close(fig)

print("Wrote", OUT)
