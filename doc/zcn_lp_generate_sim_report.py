#!/usr/bin/env python3
"""ZCN-LP scenario report: 7×6 mesh, SN on left/right mid-edge, vc_buf=4, DATA_FLITS=2.

Inputs (doc/):
  zcn_lp_sn_local_peak.csv       SN terminal metrics at λ* (max SN DAT avg per mix)
  zcn_lp_sn_local_peak_sweep.csv full λ sweep — SN DAT avg vs λ curve
  zcn_lp_sn_read_ceiling.csv     E2E read ceiling (optional; latency vs λ)
  zcn_lp_sn_write_ceiling.csv    E2E write ceiling (optional; latency vs λ)

Outputs:
  zcn_lp_sim_report.pdf   (page 1: topology + latency; page 2: utilisation)
  zcn_lp_sim_report_p1.png
  zcn_lp_sim_report_p2.png
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_CSV = os.path.join(HERE, os.environ.get("LOCAL_CSV", "zcn_lp_sn_local_peak.csv"))
SWEEP_CSV = os.path.join(HERE, os.environ.get("SWEEP_CSV", "zcn_lp_sn_local_peak_sweep.csv"))
READ_CSV = os.path.join(HERE, os.environ.get("READ_CSV", "zcn_lp_sn_read_ceiling.csv"))
WRITE_CSV = os.path.join(HERE, os.environ.get("WRITE_CSV", "zcn_lp_sn_write_ceiling.csv"))
PDF_OUT = os.path.join(HERE, "zcn_lp_sim_report.pdf")
PNG_P1 = os.path.join(HERE, "zcn_lp_sim_report_p1.png")
PNG_P2 = os.path.join(HERE, "zcn_lp_sim_report_p2.png")

VC_BUF = int(os.environ.get("ZCN_VC_BUF", "4"))
DATA_FLITS = int(os.environ.get("ZCN_DATA_FLITS", "2"))
FLIT_BYTES = 16
ROWS, COLS = 7, 6
SN_COORDS = [(3, 0), (4, 0), (3, 5), (4, 5)]
SN_ROUTERS = [r * COLS + c for r, c in SN_COORDS]

os.environ.setdefault("MPLCONFIGDIR", os.path.join(HERE, ".mplcache"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Rectangle

COL_READ = "#2563eb"
COL_WRITE = "#dc2626"
COL_SN = "#059669"
COL_REQ = "#f59e0b"
C_LINK = "#9aa0a6"
C_ROUTER = "#1565c0"
C_SN_ROUTER = "#ef6c00"
C_TERM = "#eceff1"
C_SN_FILL = "#fef3c7"
C_SN_EDGE = "#d97706"


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_sweep(path):
    rows = []
    for r in load_csv(path):
        lam = num(r.get("lambda"))
        avg = num(r.get("sn_dat_avg"))
        if lam is None or avg is None:
            continue
        rows.append({**r, "lambda": lam, "sn_dat_avg": avg})
    rows.sort(key=lambda x: (x.get("mix", ""), x["lambda"]))
    return rows


def load_latency_sweep(path, lat_keys):
    """Load λ vs packet latency from a ceiling CSV."""
    if isinstance(lat_keys, str):
        lat_keys = [lat_keys]
    rows = []
    for r in load_csv(path):
        lam = num(r.get("lambda"))
        lat = next((num(r.get(k)) for k in lat_keys if num(r.get(k)) is not None), None)
        if lam is None or lat is None:
            continue
        rows.append({"lambda": lam, "latency": lat, "state": r.get("state", "")})
    rows.sort(key=lambda x: x["lambda"])
    return rows


def best_by_avg(rows, mix):
    pts = [r for r in rows if r.get("mix") == mix]
    if not pts:
        return None
    return max(pts, key=lambda r: r["sn_dat_avg"])


def draw_topology(ax):
    """7×6 CHI mesh with 2RN+2HN per router and 4 SN/DDR on left/right mid-edge."""
    def rid(r, c):
        return r * COLS + c

    def pos(r, c):
        return (float(c), -float(r))

    for r in range(ROWS):
        for c in range(COLS):
            x, y = pos(r, c)
            if c + 1 < COLS:
                x2, y2 = pos(r, c + 1)
                ax.plot([x, x2], [y, y2], color=C_LINK, lw=1.6, zorder=1)
            if r + 1 < ROWS:
                x2, y2 = pos(r + 1, c)
                ax.plot([x, x2], [y, y2], color=C_LINK, lw=1.6, zorder=1)

    rw, rh = 0.38, 0.28
    tw, th = 0.18, 0.13
    sn_w, sn_h = 0.34, 0.18
    sn_nodes = {coord: 168 + idx for idx, coord in enumerate(SN_COORDS)}

    for r in range(ROWS):
        for c in range(COLS):
            x, y = pos(r, c)
            router = rid(r, c)
            has_sn = (r, c) in sn_nodes
            for tx, ty in (
                (x - 0.30, y + 0.26),
                (x - 0.08, y + 0.26),
                (x + 0.14, y + 0.26),
                (x + 0.36, y + 0.26),
            ):
                ax.plot([x, tx], [y, ty], color="#cfd8dc", lw=0.7, zorder=2)
                ax.add_patch(Rectangle(
                    (tx - tw / 2, ty - th / 2), tw, th,
                    facecolor=C_TERM, edgecolor="#b0bec5", lw=0.6, zorder=3))
            if has_sn:
                if c == 0:
                    sn_x = x - 0.62
                else:
                    sn_x = x + 0.62
                ax.plot([x, sn_x], [y, y], color=C_SN_EDGE, lw=1.4, zorder=2)
                ax.add_patch(Rectangle(
                    (sn_x - sn_w / 2, y - sn_h / 2), sn_w, sn_h,
                    facecolor=C_SN_FILL, edgecolor=C_SN_EDGE, lw=1.0, zorder=4))
                ax.text(sn_x, y, f"SN{sn_nodes[(r, c)]}", ha="center", va="center",
                        fontsize=5.5, color="#92400e", fontweight="bold", zorder=5)
            ax.add_patch(FancyBboxPatch(
                (x - rw / 2, y - rh / 2), rw, rh,
                boxstyle="round,pad=0.02,rounding_size=0.05",
                facecolor=C_SN_ROUTER if has_sn else C_ROUTER,
                edgecolor="none", zorder=4))
            ax.text(x, y, f"R{router}", ha="center", va="center",
                    fontsize=5.5, color="white", fontweight="bold", zorder=5)

    ax.set_xlim(-1.1, COLS + 0.1)
    ax.set_ylim(-ROWS + 0.4, 0.8)
    ax.set_aspect("equal")
    ax.axis("off")
    sn_r_str = "/".join(f"R{r}" for r in SN_ROUTERS)
    ax.set_title(
        f"Topology: 7×6 CHI mesh — 84 RN + 84 HN + 4 SN (DDR)\n"
        f"SN @ {sn_r_str} (nodes 168–171), XY routing, link_latency=2",
        fontsize=10, fontweight="bold", pad=6,
    )


def page_topology_latency(pdf, read_lat, write_lat):
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.suptitle(
        "ZCN-LP Simulation Setup\n"
        f"vc_buf_size={VC_BUF}, DATA_FLITS={DATA_FLITS}, XY, link_latency=2",
        fontsize=13, fontweight="bold", y=0.98,
    )

    ax_topo = fig.add_axes([0.04, 0.42, 0.92, 0.50])
    draw_topology(ax_topo)

    ax_lat = fig.add_axes([0.12, 0.10, 0.78, 0.26])
    plotted = False
    if read_lat:
        ok = [(r["lambda"], r["latency"]) for r in read_lat if r["state"] == "ok"]
        un = [(r["lambda"], r["latency"]) for r in read_lat if r["state"] != "ok"]
        if ok:
            ax_lat.plot(*zip(*ok), "o-", color=COL_READ, label="Read packet latency", ms=4, lw=1.5)
            plotted = True
        if un:
            ax_lat.plot(*zip(*un), "x--", color=COL_READ, alpha=0.7, label="Read (unstable)", ms=5)
            plotted = True
    if write_lat:
        ok = [(r["lambda"], r["latency"]) for r in write_lat if r["state"] == "ok"]
        un = [(r["lambda"], r["latency"]) for r in write_lat if r["state"] != "ok"]
        if ok:
            ax_lat.plot(*zip(*ok), "s-", color=COL_WRITE, label="Write packet latency", ms=4, lw=1.5)
            plotted = True
        if un:
            ax_lat.plot(*zip(*un), "x--", color=COL_WRITE, alpha=0.7, label="Write (unstable)", ms=5)
            plotted = True
    ax_lat.set_xlabel("injection rate λ (txn/node/cycle)")
    ax_lat.set_ylabel("Packet latency (cycles)")
    ax_lat.set_title("Latency vs offered load (read/write ceiling mixes)")
    ax_lat.grid(alpha=0.25)
    if plotted:
        ax_lat.legend(fontsize=8, loc="upper left")
        ymax = max(
            [r["latency"] for r in read_lat] + [r["latency"] for r in write_lat] or [100]
        )
        if ymax > 200:
            ax_lat.set_yscale("log")
    else:
        ax_lat.text(
            0.5, 0.5,
            f"No latency data\n(need {os.path.basename(READ_CSV)} / "
            f"{os.path.basename(WRITE_CSV)})",
            ha="center", va="center", transform=ax_lat.transAxes, color="#64748b",
        )

    fig.text(
        0.05, 0.02,
        "Solid markers = converged (ok). Dashed × = UNSTBL / last DisplayStats snapshot.\n"
        "Packet latency (atime-ctime, incl. source queueing) from sweep_sn_throughput ceiling CSVs.",
        fontsize=7.5, va="bottom",
        bbox=dict(boxstyle="round", fc="#f8fafc", ec="#cbd5e1"),
    )

    fig.savefig(PNG_P1, dpi=120, bbox_inches="tight")
    pdf.savefig(fig)
    plt.close(fig)


def page_utilisation(pdf, read_local, write_local, read_sweep, write_sweep):
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.suptitle(
        "ZCN-LP SN Read/Write Utilisation\n"
        f"vc_buf_size={VC_BUF} flits/VC, DATA_FLITS={DATA_FLITS}, "
        "XY routing, link_latency=2",
        fontsize=13, fontweight="bold", y=0.98,
    )

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

    bw_b = DATA_FLITS * FLIT_BYTES
    sn_r_str = "/".join(f"R{r}" for r in SN_ROUTERS)
    notes = (
        f"Config: 7×6 mesh CHI, 4 SN nodes @ {sn_r_str} (168–171), vc_buf={VC_BUF} flits/VC, "
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

    fig.savefig(PNG_P2, dpi=120, bbox_inches="tight")
    pdf.savefig(fig)
    plt.close(fig)


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
    read_lat = load_latency_sweep(READ_CSV, ["read_plat", "read_flat"])
    write_lat = load_latency_sweep(WRITE_CSV, ["write_plat", "write_flat"])

    with PdfPages(PDF_OUT) as pdf:
        page_topology_latency(pdf, read_lat, write_lat)
        page_utilisation(pdf, read_local, write_local, read_sweep, write_sweep)

    print(f"Wrote {PDF_OUT}")
    print(f"Wrote {PNG_P1}")
    print(f"Wrote {PNG_P2}")


if __name__ == "__main__":
    main()
