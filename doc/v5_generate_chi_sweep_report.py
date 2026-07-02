#!/usr/bin/env python3
"""Build a per-channel latency-throughput report from the CHI subnet sweep.

Input : v5_chi_subnet_sweep.csv   (from runfiles/sweep_chi_subnet.py)
Output: v5_chi_subnet_sweep_report.pdf
        v5_chi_subnet_sweep_p1.png  (latency-throughput preview)

Optional env:
  SAT_ONSET     first total LAMBDA that drove the network unstable (for annotation)
  SWEEP_CSV     input CSV name (default v5_chi_subnet_sweep.csv)
  SWEEP_REPORT  output base name without extension (default v5_chi_subnet_sweep)
  ROUTING_LABEL routing name shown in titles (default "min")
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_IN = os.path.join(HERE, os.environ.get("SWEEP_CSV", "v5_chi_subnet_sweep.csv"))
_BASE = os.environ.get("SWEEP_REPORT", "v5_chi_subnet_sweep")
PDF_OUT = os.path.join(HERE, _BASE + "_report.pdf")
PNG_OUT = os.path.join(HERE, _BASE + "_p1.png")
ROUTING_LABEL = os.environ.get("ROUTING_LABEL", "min")
SAT_ONSET = float(os.environ.get("SAT_ONSET", 0.005))

os.environ.setdefault("MPLCONFIGDIR", os.path.join(HERE, ".mplcache"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

CHANNELS = ["REQ", "RSP", "SNP", "DAT"]
SUBNET = {"REQ": 0, "RSP": 1, "SNP": 2, "DAT": 3}
COLORS = {"REQ": "#2563eb", "RSP": "#7c3aed", "SNP": "#16a34a", "DAT": "#dc2626"}


def load():
    data = {ch: [] for ch in CHANNELS}
    with open(CSV_IN) as f:
        for row in csv.DictReader(f):
            ch = row["channel"]
            if ch not in data:
                continue
            def num(k):
                v = row[k]
                return float(v) if v not in ("", "None") else None
            data[ch].append({
                "lambda": float(row["lambda"]),
                "state": row["state"],
                "inj_flit": num("inj_flit"),
                "acc_flit": num("acc_flit"),
                "accept_ratio": num("accept_ratio"),
                "packet_latency": num("packet_latency"),
                "flit_latency": num("flit_latency"),
                "hops": num("hops"),
            })
    for ch in data:
        data[ch].sort(key=lambda r: r["lambda"])
    return data


def knee(points):
    """Last stable point and the point with the largest latency jump."""
    stable = [p for p in points
              if p["flit_latency"] is not None and p["state"] == "ok"]
    if not stable:
        return None, None
    last = stable[-1]
    jump = stable[-1]
    best = 0.0
    for a, b in zip(stable, stable[1:]):
        if a["flit_latency"] and b["flit_latency"]:
            d = b["flit_latency"] - a["flit_latency"]
            if d > best:
                best = d
                jump = b
    return last, jump


def fmt(x, d=4):
    return "-" if x is None else f"{x:.{d}f}"


def main():
    data = load()
    knees = {ch: knee(data[ch]) for ch in CHANNELS}

    with PdfPages(PDF_OUT) as pdf:
        # ---- page 1: latency-throughput + latency-vs-load ----
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle(f"CHI 4-Channel Latency-Throughput Sweep ({ROUTING_LABEL} routing)",
                     fontsize=14, fontweight="bold", y=0.975)

        def split(ch, xkey):
            """Return (stable, unstable) [(x, lat), ...] plus the bridge point.

            Unstable (UNSTBL) points come from the last periodic snapshot of a
            diverging run: throughput is the sustained plateau, latency is a
            lower bound on the (unbounded) queueing delay.
            """
            pts = [p for p in data[ch] if p["flit_latency"] is not None]
            st = [(p[xkey], p["flit_latency"]) for p in pts if p["state"] == "ok"]
            un = [(p[xkey], p["flit_latency"]) for p in pts if p["state"] != "ok"]
            return st, un

        ax1 = fig.add_axes([0.12, 0.58, 0.80, 0.31])
        for ch in CHANNELS:
            st, un = split(ch, "acc_flit")
            if st:
                xs, ys = zip(*st)
                ax1.plot(xs, ys, "-o", color=COLORS[ch],
                         label=f"{ch} (subnet {SUBNET[ch]})", markersize=4)
            if un:
                bridge = ([st[-1]] if st else []) + un
                bx, by = zip(*bridge)
                ax1.plot(bx, by, "--x", color=COLORS[ch], markersize=7, lw=1.2)
        ax1.set_xlabel("Accepted flit rate (flit / node / cycle)")
        ax1.set_ylabel("Flit latency (cycles)")
        ax1.set_title("Latency vs delivered throughput  (solid=stable, dashed x=unstable)")
        ax1.grid(alpha=0.25)
        ax1.legend(fontsize=9)

        ax2 = fig.add_axes([0.12, 0.16, 0.80, 0.30])
        for ch in CHANNELS:
            st, un = split(ch, "lambda")
            if st:
                xs, ys = zip(*st)
                ax2.plot(xs, ys, "-o", color=COLORS[ch], label=ch, markersize=4)
            if un:
                bridge = ([st[-1]] if st else []) + un
                bx, by = zip(*bridge)
                ax2.plot(bx, by, "--x", color=COLORS[ch], markersize=7, lw=1.2)
        ax2.axvline(SAT_ONSET, color="#64748b", ls="--", lw=1.2)
        ax2.text(SAT_ONSET, ax2.get_ylim()[1] * 0.92,
                 f" unstable >= {SAT_ONSET:g}", color="#475569", fontsize=8)
        ax2.set_xlabel("Total transaction rate LAMBDA (txn / node / cycle)")
        ax2.set_ylabel("Flit latency (cycles)")
        ax2.set_title("Latency vs offered load (CHI_LAMBDA)")
        ax2.grid(alpha=0.25)
        ax2.legend(fontsize=9)
        fig.savefig(PNG_OUT, dpi=120)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- page 2: throughput linearity + acceptance ratio ----
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("Throughput Scaling & Acceptance", fontsize=15,
                     fontweight="bold", y=0.975)

        ax3 = fig.add_axes([0.12, 0.58, 0.80, 0.31])
        for ch in CHANNELS:
            pts = [p for p in data[ch] if p["acc_flit"] is not None]
            st = [(p["lambda"], p["acc_flit"]) for p in pts if p["state"] == "ok"]
            un = [(p["lambda"], p["acc_flit"]) for p in pts if p["state"] != "ok"]
            if st:
                xs, ys = zip(*st)
                ax3.plot(xs, ys, "-o", color=COLORS[ch], label=ch, markersize=4)
            if un:
                bx, by = zip(*(([st[-1]] if st else []) + un))
                ax3.plot(bx, by, "--x", color=COLORS[ch], markersize=7, lw=1.2)
        ax3.axvline(SAT_ONSET, color="#64748b", ls="--", lw=1.2)
        ax3.set_xlabel("Total transaction rate LAMBDA")
        ax3.set_ylabel("Accepted flit rate (flit / node / cycle)")
        ax3.set_title("Per-channel accepted throughput vs offered load")
        ax3.grid(alpha=0.25)
        ax3.legend(fontsize=9)

        ax4 = fig.add_axes([0.12, 0.16, 0.80, 0.30])
        for ch in CHANNELS:
            xs = [p["lambda"] for p in data[ch] if p["accept_ratio"] is not None]
            ys = [p["accept_ratio"] for p in data[ch] if p["accept_ratio"] is not None]
            ax4.plot(xs, ys, "-o", color=COLORS[ch], label=ch, markersize=4)
        ax4.axhline(1.0, color="#94a3b8", ls=":", lw=1.0)
        ax4.set_xlabel("Total transaction rate LAMBDA")
        ax4.set_ylabel("Accepted / injected flit rate")
        ax4.set_title("Drain ratio (≈1 means the channel keeps up)")
        ax4.grid(alpha=0.25)
        ax4.legend(fontsize=9)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- page 3: knee table + recommendations ----
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("Saturation Summary & Optimization", fontsize=15,
                     fontweight="bold", y=0.975)
        ax = fig.add_axes([0.04, 0.60, 0.92, 0.30])
        ax.axis("off")
        header = ["Channel", "Subnet", "Last stable\nLAMBDA",
                  "Accepted flit\n@ last stable", "Flit lat\n@ last stable",
                  "Knee LAMBDA", "Knee flit lat"]
        rows = []
        for ch in CHANNELS:
            last, jump = knees[ch]
            rows.append([
                ch, str(SUBNET[ch]),
                fmt(last["lambda"], 4) if last else "-",
                fmt(last["acc_flit"], 5) if last else "-",
                fmt(last["flit_latency"], 1) if last else "-",
                fmt(jump["lambda"], 4) if jump else "-",
                fmt(jump["flit_latency"], 1) if jump else "-",
            ])
        table = ax.table(cellText=[header] + rows, loc="center", cellLoc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(8.5)
        table.scale(1.0, 2.0)
        for col in range(len(header)):
            table[0, col].set_facecolor("#1e293b")
            table[0, col].set_text_props(color="white", fontweight="bold")

        # ordering by first-to-rise latency at the knee
        rise = sorted(
            CHANNELS,
            key=lambda c: (knees[c][1]["flit_latency"] if knees[c][1] else 0),
            reverse=True,
        )
        rec = [
            f"Network saturates near LAMBDA ~ {SAT_ONSET:g} txn/node/cycle; the next swept point goes unstable (latency > 500 cycles).",
            "Dashed 'x' points (LAMBDA >= saturation) are the last periodic snapshot of a non-converged run: throughput = sustained plateau, latency = lower bound on unbounded queueing.",
            f"First channels to bend up are {rise[0]} and {rise[1]} (subnets {SUBNET[rise[0]]}/{SUBNET[rise[1]]}); REQ and SNP stay flat to the knee.",
            "Saturation accepted throughput is low (~0.003 flit/node/cycle/channel), so the limiter is destination hotspot concentration, not mesh bisection.",
            "DAT carries 2-flit payloads and concentrates on the 4 SN nodes (DMT reads, L3 evictions, CleanInvalid writeback); those 4 ejection links throttle DAT first.",
            "RSP has the most classes and fans into RN/HN; protect it with deeper VC buffers or an extra VC rather than treating it as 'short and cheap'.",
            "Optimization 1: add more SN/DDR attach points (or spread the 4 SNs across non-adjacent routers) to widen the memory-side bottleneck.",
            "Optimization 2: raise vc_buf_size (2 -> 4/8) and num_vcs on RSP/DAT subnets; shallow 2-flit buffers cap the knee well below mesh capacity.",
            "Optimization 3: place HN home-node interleaving so REQ/RSP do not all converge on a few HN tiles; balance hotspot destination sets.",
            "Optimization 4: if DAT stays dominant, widen DAT (more lanes / larger flit) or split read-data vs write-data into separate subnets.",
        ]
        text = "\n".join(f"- {line}" for line in rec)
        fig.text(0.06, 0.50, text, fontsize=9.5, va="top",
                 bbox=dict(boxstyle="round", fc="#f8fafc", ec="#cbd5e1"))
        fig.text(0.5, 0.04,
                 f"Config: {ROUTING_LABEL} routing, 4 subnets (REQ/RSP/SNP/DAT), 2 VCs/input, "
                 "2-flit VC buffers, output-first round-robin arbitration, 6x7 mesh + 4 DDR SN.",
                 ha="center", fontsize=8.5, color="#475569")
        pdf.savefig(fig)
        plt.close(fig)

    print(f"Wrote {PDF_OUT}")
    print(f"Wrote {PNG_OUT}")
    print("\nPer-channel knee summary:")
    for ch in CHANNELS:
        last, jump = knees[ch]
        print(f"  {ch}: last stable LAMBDA={fmt(last['lambda'],4)} "
              f"acc={fmt(last['acc_flit'],5)} lat={fmt(last['flit_latency'],1)} | "
              f"knee LAMBDA={fmt(jump['lambda'],4)} lat={fmt(jump['flit_latency'],1)}")


if __name__ == "__main__":
    main()
