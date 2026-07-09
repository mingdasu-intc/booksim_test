#!/usr/bin/env python3
"""Render the 4-channel CHI mesh injection-rate sweep into a PDF chart report.

Reads runfiles/chi_sweep_results.csv and writes doc/v2_mesh6x7_chi_4channel_report.pdf
(2 pages: latency-throughput curves + accepted-rate / data table).
"""
import os, csv

# matplotlib needs a writable config dir in this sandbox
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("MPLCONFIGDIR", os.path.join(HERE, ".mplcache"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

CSV = os.path.join(HERE, "..", "runfiles", "chi_sweep_results.csv")
OUT = os.path.join(HERE, "v2_mesh6x7_chi_4channel_report.pdf")

off, lat0, acc0, lat1, acc1 = [], [], [], [], []
sat_x = None
with open(CSV) as f:
    for row in csv.DictReader(f):
        x = float(row["offered_inj"])
        if row["state"] == "SAT" or not row["lat_c0"]:
            sat_x = x
            continue
        off.append(x)
        lat0.append(float(row["lat_c0"]));  acc0.append(float(row["acc_c0"]))
        lat1.append(float(row["lat_c1"]));  acc1.append(float(row["acc_c1"]))

# knee = last stable point before saturation
knee_x = off[-1]
C0 = "#2563eb"  # REQ/DAT
C1 = "#dc2626"  # SNP/RSP

with PdfPages(OUT) as pdf:
    # ---------- Page 1: latency vs offered load + acc vs offered load ----------
    fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
    fig.suptitle("6x7 Mesh + CHI 4 Independent Physical Channels\n"
                 "Injection-Rate Sweep (snoop_factor = 1.0)",
                 fontsize=15, fontweight="bold", y=0.97)

    ax1 = fig.add_axes([0.12, 0.57, 0.78, 0.32])
    ax1.plot(off, lat0, "o-", color=C0, label="REQ/DAT (class 0)")
    ax1.plot(off, lat1, "s-", color=C1, label="SNP/RSP (class 1)")
    if sat_x is not None:
        ax1.axvline(sat_x, color="gray", ls="--", lw=1)
        ax1.text(sat_x, ax1.get_ylim()[1]*0.5, f" saturation\n @ {sat_x}",
                 color="gray", fontsize=9, va="center")
    ax1.set_xlabel("Offered load (injection rate / node / class)")
    ax1.set_ylabel("Average packet latency (cycles)")
    ax1.set_title("Latency vs. Offered Load", fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    ax2 = fig.add_axes([0.12, 0.13, 0.78, 0.32])
    ax2.plot(off, acc0, "o-", color=C0, label="REQ/DAT (class 0)")
    ax2.plot(off, acc1, "s-", color=C1, label="SNP/RSP (class 1)")
    ax2.set_xlabel("Offered load (injection rate / node / class)")
    ax2.set_ylabel("Accepted flit rate (flit / node / cycle)")
    ax2.set_title("Throughput vs. Offered Load", fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    fig.text(0.5, 0.05,
             f"Saturation knee ~ offered {knee_x} / node / class   |   "
             f"168 nodes (84 RN + 84 HN), subnets=4, num_vcs=2",
             ha="center", fontsize=9, color="#444")
    fig.savefig(os.path.join(HERE, "v2_mesh6x7_chi_4channel_report_p1.png"), dpi=110)
    pdf.savefig(fig); plt.close(fig)

    # ---------- Page 2: channel mapping + data table ----------
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.suptitle("CHI Channel Mapping & Sweep Data", fontsize=15,
                 fontweight="bold", y=0.97)

    ax3 = fig.add_axes([0.08, 0.62, 0.84, 0.26]); ax3.axis("off")
    map_rows = [
        ["CHI channel", "BookSim type", "subnet", "size", "direction"],
        ["REQ", "read_request", "0", "1 flit", "RN -> HN"],
        ["DAT", "read_reply", "1", "5 flit", "HN -> RN"],
        ["SNP", "write_request", "2", "1 flit", "-> RN"],
        ["RSP", "write_reply", "3", "1 flit", "RN ->"],
    ]
    t1 = ax3.table(cellText=map_rows, loc="center", cellLoc="center")
    t1.auto_set_font_size(False); t1.set_fontsize(10); t1.scale(1, 1.6)
    for c in range(5):
        t1[0, c].set_facecolor("#1e293b"); t1[0, c].set_text_props(color="white", fontweight="bold")
    ax3.set_title("4 channels -> 4 independent physical networks", fontsize=12, pad=14)

    ax4 = fig.add_axes([0.06, 0.10, 0.88, 0.42]); ax4.axis("off")
    hdr = ["offered", "REQ/DAT lat", "REQ/DAT acc", "SNP/RSP lat", "SNP/RSP acc"]
    data = [[f"{off[i]}", f"{lat0[i]:.1f}", f"{acc0[i]:.4f}",
             f"{lat1[i]:.1f}", f"{acc1[i]:.4f}"] for i in range(len(off))]
    if sat_x is not None:
        data.append([f"{sat_x}", "SAT", "-", "SAT", "-"])
    t2 = ax4.table(cellText=[hdr] + data, loc="center", cellLoc="center")
    t2.auto_set_font_size(False); t2.set_fontsize(10); t2.scale(1, 1.5)
    for c in range(5):
        t2[0, c].set_facecolor("#1e293b"); t2[0, c].set_text_props(color="white", fontweight="bold")
    # highlight the knee row
    knee_row = len(off)
    for c in range(5):
        t2[knee_row, c].set_facecolor("#fde68a")
    ax4.set_title("Sweep results (latency in cycles, acc in flit/node/cycle)",
                  fontsize=12, pad=14)

    fig.text(0.5, 0.05, "Highlighted row = last stable point before saturation (knee).",
             ha="center", fontsize=9, color="#444")
    pdf.savefig(fig); plt.close(fig)

print("Wrote", OUT)
