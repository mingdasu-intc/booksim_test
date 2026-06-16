#!/usr/bin/env python3
"""Generate a PDF report comparing uniform vs hotspot cache-coherence traffic
on the 6x7 BookSim mesh. Data come from utils/sweep.sh runs.

Usage: python3 generate_coherence_report.py
Output: mesh6x7_coherence_report.pdf (next to this script)
"""
import os

# Sandbox-friendly matplotlib cache dir (default ~/.matplotlib is not writable).
os.environ.setdefault(
    "MPLCONFIGDIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mplcache")
)
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# --- Sweep data (offered load pkt/node/cyc, accepted throughput flit/node/cyc, latency cyc) ---
UNIFORM = [
    (0.0025, 0.0154, 30.36),
    (0.0500, 0.3035, 33.84),
    (0.0625, 0.3759, 38.10),
    (0.0656, 0.3953, 39.34),
    (0.0672, 0.4030, 39.69),
]
HOTSPOT = [
    (0.0025, 0.0153, 30.24),
    (0.0125, 0.0764, 32.06),
    (0.0188, 0.1123, 35.88),
    (0.0219, 0.1302, 59.07),
    (0.0234, 0.1366, 281.25),
]

U_SAT_INJ, H_SAT_INJ = 0.0672, 0.0234
U_PEAK_THR, H_PEAK_THR = 0.403, 0.137

C_UNIFORM = "#2e7d32"  # green
C_HOTSPOT = "#ef6c00"  # orange
C_TEXT = "#1a1a1a"
C_MUTED = "#666666"

u_inj = [p[0] for p in UNIFORM]
u_thr = [p[1] for p in UNIFORM]
u_lat = [p[2] for p in UNIFORM]
h_inj = [p[0] for p in HOTSPOT]
h_thr = [p[1] for p in HOTSPOT]
h_lat = [p[2] for p in HOTSPOT]

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "mesh6x7_coherence_report.pdf")

with PdfPages(out_path) as pdf:
    # ===================== Page 1: summary + bar chart =====================
    fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
    fig.subplots_adjust(left=0.09, right=0.94, top=0.95, bottom=0.07)

    fig.text(0.09, 0.945, "Cache-Coherence Traffic on a 6\u00d77 Mesh",
             fontsize=19, fontweight="bold", color=C_TEXT)
    fig.text(0.09, 0.925, "Uniform (distributed directory) vs. Hotspot (4 centralized directories)",
             fontsize=11.5, color=C_MUTED)
    fig.text(0.09, 0.905,
             "BookSim2 \u00b7 anynet 42-node mesh \u00b7 request/reply \u00b7 write_fraction 0.3 \u00b7 "
             "1-flit control / 5-flit data \u00b7 2 subnets \u00b7 4 VCs",
             fontsize=8.5, color=C_MUTED)

    # Summary stat boxes
    stats = [
        ("Uniform peak throughput", f"{U_PEAK_THR:.2f}", "flits/node/cyc", C_UNIFORM),
        ("Hotspot peak throughput", f"{H_PEAK_THR:.2f}", "flits/node/cyc", C_HOTSPOT),
        ("Uniform saturation load", f"{U_SAT_INJ:.4f}", "pkt/node/cyc", C_TEXT),
        ("Hotspot saturation load", f"{H_SAT_INJ:.4f}", "pkt/node/cyc", C_TEXT),
    ]
    box_y = 0.83
    for i, (label, val, unit, color) in enumerate(stats):
        x = 0.09 + (i % 2) * 0.44
        y = box_y - (i // 2) * 0.09
        ax = fig.add_axes([x, y, 0.40, 0.075])
        ax.axis("off")
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                                   facecolor="#f5f5f5", edgecolor="#dddddd"))
        ax.text(0.05, 0.62, val, fontsize=20, fontweight="bold", color=color,
                transform=ax.transAxes)
        ax.text(0.05, 0.30, label, fontsize=9, color=C_TEXT, transform=ax.transAxes)
        ax.text(0.05, 0.10, unit, fontsize=7.5, color=C_MUTED, transform=ax.transAxes)

    # Key findings
    findings = (
        "Key findings\n"
        "\u2022 At low load both patterns behave identically (avg hop count \u2248 5.1, "
        "zero-load latency \u2248 30 cyc).\n"
        "\u2022 Distributing directories across all nodes sustains ~0.40 flits/node/cyc; "
        "funneling all\n   requests into 4 hotspot banks collapses this to ~0.14 \u2014 about 2.9\u00d7 lower.\n"
        "\u2022 Hotspot saturates at ~1/3 the offered load and its latency blows up sharply "
        "(to 281 cyc),\n   because the hotspot nodes' ejection ports and the links feeding "
        "them become the bottleneck.\n"
        "\u2022 Conclusion: a centralized coherence directory is a throughput bottleneck; "
        "distributing the\n   home nodes is essential for scalable coherence traffic."
    )
    fig.text(0.09, 0.52, findings, fontsize=9.5, color=C_TEXT, va="top", linespacing=1.6)

    # Bar chart: peak throughput
    ax_bar = fig.add_axes([0.12, 0.07, 0.78, 0.30])
    bars = ax_bar.bar(["Uniform\n(distributed)", "Hotspot\n(4 dirs)"],
                      [U_PEAK_THR, H_PEAK_THR],
                      color=[C_UNIFORM, C_HOTSPOT], width=0.55)
    ax_bar.set_ylabel("Peak accepted throughput (flits/node/cyc)", fontsize=9.5)
    ax_bar.set_title("Peak sustained throughput (higher is better)", fontsize=11,
                     fontweight="bold")
    ax_bar.spines[["top", "right"]].set_visible(False)
    for b, v in zip(bars, [U_PEAK_THR, H_PEAK_THR]):
        ax_bar.text(b.get_x() + b.get_width() / 2, v + 0.008, f"{v:.3f}",
                    ha="center", fontsize=10, fontweight="bold")
    ax_bar.set_ylim(0, 0.46)

    pdf.savefig(fig)
    plt.close(fig)

    # ===================== Page 2: curves =====================
    fig2, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.27, 11.69))
    fig2.subplots_adjust(left=0.11, right=0.94, top=0.93, bottom=0.22, hspace=0.28)

    fig2.suptitle("Latency-Throughput Characteristics", fontsize=16,
                  fontweight="bold", x=0.11, ha="left", y=0.965)

    # Latency vs offered load
    ax1.plot(u_inj, u_lat, "o-", color=C_UNIFORM, label="Uniform", linewidth=2, markersize=6)
    ax1.plot(h_inj, h_lat, "s-", color=C_HOTSPOT, label="Hotspot (4 dirs)", linewidth=2, markersize=6)
    ax1.set_xlabel("Offered load (pkt/node/cyc)", fontsize=10)
    ax1.set_ylabel("Average packet latency (cyc)", fontsize=10)
    ax1.set_title("Average packet latency vs. offered load", fontsize=12, fontweight="bold")
    ax1.legend(frameon=False, fontsize=10)
    ax1.grid(True, alpha=0.25)
    ax1.spines[["top", "right"]].set_visible(False)

    # Throughput vs offered load
    ax2.plot(u_inj, u_thr, "o-", color=C_UNIFORM, label="Uniform", linewidth=2, markersize=6)
    ax2.plot(h_inj, h_thr, "s-", color=C_HOTSPOT, label="Hotspot (4 dirs)", linewidth=2, markersize=6)
    ax2.axhline(U_PEAK_THR, color=C_UNIFORM, ls="--", alpha=0.5, linewidth=1)
    ax2.axhline(H_PEAK_THR, color=C_HOTSPOT, ls="--", alpha=0.5, linewidth=1)
    ax2.set_xlabel("Offered load (pkt/node/cyc)", fontsize=10)
    ax2.set_ylabel("Accepted throughput (flits/node/cyc)", fontsize=10)
    ax2.set_title("Accepted throughput vs. offered load", fontsize=12, fontweight="bold")
    ax2.legend(frameon=False, fontsize=10, loc="upper left")
    ax2.grid(True, alpha=0.25)
    ax2.spines[["top", "right"]].set_visible(False)

    # Data tables below as figure text
    def fmt_table(title, data):
        lines = [title, f"{'load':>8} {'thrpt':>8} {'lat':>9}"]
        for inj, thr, lat in data:
            lines.append(f"{inj:>8.4f} {thr:>8.4f} {lat:>9.2f}")
        return "\n".join(lines)

    fig2.text(0.11, 0.175, "Sweep data points", fontsize=11, fontweight="bold",
              color=C_TEXT, va="top")
    fig2.text(0.11, 0.15, fmt_table("Uniform", UNIFORM), fontsize=8.5,
              family="monospace", color=C_TEXT, va="top")
    fig2.text(0.55, 0.15, fmt_table("Hotspot (4 dirs)", HOTSPOT), fontsize=8.5,
              family="monospace", color=C_TEXT, va="top")

    pdf.savefig(fig2)
    if os.environ.get("DUMP_PNG"):
        fig2.savefig(os.path.join(os.path.dirname(out_path), "_page2.png"), dpi=110)
    plt.close(fig2)

    d = pdf.infodict()
    d["Title"] = "6x7 Mesh Coherence Traffic: Uniform vs Hotspot"
    d["Subject"] = "BookSim2 latency-throughput comparison"

print("Wrote", out_path)
