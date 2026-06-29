#!/usr/bin/env python3
"""Draw the 6x7 CHI mesh with 2RN+2HN per router and 4 top-row SN/DDR nodes."""
import os

os.environ.setdefault(
    "MPLCONFIGDIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mplcache")
)
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

ROWS, COLS = 6, 7
SN_COORDS = [(0, 1), (0, 2), (0, 4), (0, 5)]

C_LINK = "#9aa0a6"
C_ROUTER = "#1565c0"
C_SN_ROUTER = "#ef6c00"
C_TERM = "#eceff1"
C_SN = "#fef3c7"
C_SN_EDGE = "#d97706"
C_TEXT = "#ffffff"

def rid(r, c):
    return r * COLS + c

def pos(r, c):
    return (float(c), -float(r))

fig, ax = plt.subplots(figsize=(12.5, 9.4))

# mesh links
for r in range(ROWS):
    for c in range(COLS):
        x, y = pos(r, c)
        if c + 1 < COLS:
            x2, y2 = pos(r, c + 1)
            ax.plot([x, x2], [y, y2], color=C_LINK, lw=2.0, zorder=1)
        if r + 1 < ROWS:
            x2, y2 = pos(r + 1, c)
            ax.plot([x, x2], [y, y2], color=C_LINK, lw=2.0, zorder=1)

rw, rh = 0.42, 0.30
tw, th = 0.22, 0.16
sn_w, sn_h = 0.38, 0.20

sn_nodes = {coord: 168 + idx for idx, coord in enumerate(SN_COORDS)}

for r in range(ROWS):
    for c in range(COLS):
        x, y = pos(r, c)
        router = rid(r, c)
        has_sn = (r, c) in sn_nodes

        # four RN/HN terminals near each router
        labels = [
            (f"RN{2*router}", x - 0.34, y + 0.30),
            (f"RN{2*router+1}", x - 0.10, y + 0.30),
            (f"HN{2*router}", x + 0.14, y + 0.30),
            (f"HN{2*router+1}", x + 0.38, y + 0.30),
        ]
        for label, tx, ty in labels:
            ax.plot([x, tx], [y, ty], color="#cfd8dc", lw=1.0, zorder=2)
            ax.add_patch(Rectangle((tx - tw / 2, ty - th / 2), tw, th,
                                   facecolor=C_TERM, edgecolor="#b0bec5", lw=0.8, zorder=3))
            ax.text(tx, ty, label, ha="center", va="center", fontsize=4.6,
                    color="#455a64", zorder=4)

        if has_sn:
            sn_y = y + 0.68
            ax.plot([x, x], [y, sn_y], color=C_SN_EDGE, lw=1.8, zorder=2)
            ax.add_patch(Rectangle((x - sn_w / 2, sn_y - sn_h / 2), sn_w, sn_h,
                                   facecolor=C_SN, edgecolor=C_SN_EDGE, lw=1.1, zorder=4))
            ax.text(x, sn_y, f"SN{sn_nodes[(r, c)]}\nDDR", ha="center", va="center",
                    fontsize=6.0, color="#92400e", fontweight="bold", zorder=5)

        ax.add_patch(FancyBboxPatch((x - rw / 2, y - rh / 2), rw, rh,
                                    boxstyle="round,pad=0.02,rounding_size=0.06",
                                    facecolor=C_SN_ROUTER if has_sn else C_ROUTER,
                                    edgecolor="none", zorder=4))
        ax.text(x, y, f"R{router}\n({r},{c})", ha="center", va="center",
                fontsize=6.8, color=C_TEXT, fontweight="bold", zorder=5)

for c in range(COLS):
    ax.text(c, 1.10, f"col {c}", ha="center", va="center", fontsize=8, color="#90a4ae")
for r in range(ROWS):
    ax.text(-0.82, -r, f"row {r}", ha="center", va="center", fontsize=8, color="#90a4ae")

ax.set_title("6x7 CHI Mesh: 2RN+2HN per Router + 4 SN/DDR Nodes",
             fontsize=14, fontweight="bold", pad=14)

ax.text(-0.4, -6.08,
        "SN placement: R1(0,1)->node168, R2(0,2)->node169, "
        "R4(0,4)->node170, R5(0,5)->node171",
        fontsize=9, color="#444")
ax.text(-0.4, -6.34,
        "Total terminals: 84 RN + 84 HN + 4 SN = 172 nodes. "
        "SN nodes are direct router terminals used to model DDR access.",
        fontsize=8.5, color="#666")

ax.set_xlim(-1.1, COLS - 0.25)
ax.set_ylim(-6.55, 1.35)
ax.set_aspect("equal")
ax.axis("off")

base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mesh6x7_chi_sn_topology")
fig.savefig(base + ".png", dpi=140, bbox_inches="tight")
fig.savefig(base + ".pdf", bbox_inches="tight")
print("Wrote", base + ".png and .pdf")
