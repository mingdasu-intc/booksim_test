#!/usr/bin/env python3
"""Draw the 6x7 (42-node) BookSim mesh topology.
Router id = row*COLS + col (matches runfiles/mesh6x7_anynet).
Output: mesh6x7_topology.png / .pdf next to this script.
"""
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
HOTSPOTS = {8, 12, 29, 33}  # the 4 directory/MC nodes from the hotspot config

C_LINK = "#9aa0a6"
C_ROUTER = "#1565c0"
C_ROUTER_HS = "#ef6c00"
C_PE = "#eceff1"
C_PE_EDGE = "#b0bec5"
C_INJ = "#cfd8dc"
C_TEXT = "#ffffff"

def rid(r, c):
    return r * COLS + c

fig, ax = plt.subplots(figsize=(12, 9.2))

# x = col, y = -row so that row 0 is at the top
def pos(r, c):
    return (c * 1.0, -r * 1.0)

# --- mesh links (draw first, behind nodes) ---
for r in range(ROWS):
    for c in range(COLS):
        x, y = pos(r, c)
        if c + 1 < COLS:
            x2, y2 = pos(r, c + 1)
            ax.plot([x, x2], [y, y2], color=C_LINK, lw=2.2, zorder=1)
        if r + 1 < ROWS:
            x2, y2 = pos(r + 1, c)
            ax.plot([x, x2], [y, y2], color=C_LINK, lw=2.2, zorder=1)

# --- routers + attached PEs ---
rw, rh = 0.42, 0.30          # router box
pew, peh = 0.30, 0.20        # PE box
for r in range(ROWS):
    for c in range(COLS):
        x, y = pos(r, c)
        i = rid(r, c)
        is_hs = i in HOTSPOTS

        # PE (processing element) attached above-right of the router via injection link
        pex, pey = x + 0.30, y + 0.30
        ax.plot([x, pex], [y, pey], color=C_INJ, lw=1.6, zorder=2)
        ax.add_patch(Rectangle((pex - pew / 2, pey - peh / 2), pew, peh,
                               facecolor=C_PE, edgecolor=C_PE_EDGE, lw=1.0, zorder=3))
        ax.text(pex, pey, f"PE{i}", ha="center", va="center", fontsize=5.5,
                color="#455a64", zorder=4)

        # router
        ax.add_patch(FancyBboxPatch((x - rw / 2, y - rh / 2), rw, rh,
                                    boxstyle="round,pad=0.02,rounding_size=0.06",
                                    facecolor=C_ROUTER_HS if is_hs else C_ROUTER,
                                    edgecolor="none", zorder=4))
        ax.text(x, y, f"R{i}", ha="center", va="center", fontsize=8.5,
                color=C_TEXT, fontweight="bold", zorder=5)

# --- coordinate guides ---
for c in range(COLS):
    ax.text(c, 0.72, f"col {c}", ha="center", va="center", fontsize=8, color="#90a4ae")
for r in range(ROWS):
    ax.text(-0.72, -r, f"row {r}", ha="center", va="center", fontsize=8, color="#90a4ae")

ax.set_title("6\u00d77 Mesh Topology (42 routers, 42 nodes) \u2014 BookSim anynet",
             fontsize=14, fontweight="bold", pad=14)

# legend
ax.add_patch(FancyBboxPatch((0.1, -5.85), 0.34, 0.26,
             boxstyle="round,pad=0.02,rounding_size=0.06",
             facecolor=C_ROUTER, edgecolor="none"))
ax.text(0.55, -5.72, "router", fontsize=9, va="center", color="#333")
ax.add_patch(FancyBboxPatch((1.7, -5.85), 0.34, 0.26,
             boxstyle="round,pad=0.02,rounding_size=0.06",
             facecolor=C_ROUTER_HS, edgecolor="none"))
ax.text(2.15, -5.72, "hotspot directory node (8,12,29,33)", fontsize=9, va="center", color="#333")
ax.add_patch(Rectangle((5.5, -5.82), 0.28, 0.19, facecolor=C_PE, edgecolor=C_PE_EDGE))
ax.text(5.9, -5.72, "PE (terminal)", fontsize=9, va="center", color="#333")

ax.text(0.1, -6.15,
        "Router id = row\u00d77 + col \u00b7 each router has 1 PE (inject/eject) \u00b7 "
        "degree: corner 2, edge 3, interior 4 \u00b7 bidirectional links",
        fontsize=8.5, color="#666")

ax.set_xlim(-1.3, COLS - 0.2)
ax.set_ylim(-6.4, 1.1)
ax.set_aspect("equal")
ax.axis("off")

base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mesh6x7_topology")
fig.savefig(base + ".png", dpi=130, bbox_inches="tight")
fig.savefig(base + ".pdf", bbox_inches="tight")
print("Wrote", base + ".png and .pdf")
