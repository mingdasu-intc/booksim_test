#!/usr/bin/env python3
"""Report SN local terminal peaks vs E2E DAT utilisation.

Input : v6_repair_sn_local_peak.csv
Output: v6_repair_sn_local_peak_report.pdf, v6_repair_sn_local_peak_p1.png
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_IN = os.path.join(HERE, os.environ.get("CSV_IN", "v6_repair_sn_local_peak.csv"))
PDF_OUT = os.path.join(HERE, "v6_repair_sn_local_peak_report.pdf")
PNG_OUT = os.path.join(HERE, "v6_repair_sn_local_peak_p1.png")

os.environ.setdefault("MPLCONFIGDIR", os.path.join(HERE, ".mplcache"))
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def load():
    rows = []
    with open(CSV_IN) as f:
        for r in csv.DictReader(f):
            rows.append({k: r[k] for k in r})
    return rows


def main():
    rows = load()
    if not rows:
        print(f"No data in {CSV_IN}")
        return

    with PdfPages(PDF_OUT) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("SN Terminal Local Peaks vs E2E DAT Utilisation\n"
                     "(DATA_FLITS=%s, read/write ceiling mixes)" % rows[0].get("data_flits", "?"),
                     fontsize=13, fontweight="bold", y=0.975)

        ax = fig.add_axes([0.10, 0.52, 0.85, 0.38])
        labels, xloc = [], []
        sn_dat, e2e, sn_req = [], [], []
        for i, r in enumerate(rows):
            labels.append(f"{r['mix']}\nbuf={r['vc_buf_size']}")
            xloc.append(i)
            sn_dat.append(float(r["sn_dat_peak"]) * 100)
            e2e.append(float(r["e2e_dat_util"]) * 100)
            sn_req.append(float(r["sn_req_peak"]) * 100)
        w = 0.25
        ax.bar([x - w for x in xloc], sn_dat, width=w, label="SN local DAT peak", color="#2563eb")
        ax.bar(xloc, e2e, width=w, label="E2E DAT util (old metric)", color="#93c5fd")
        ax.bar([x + w for x in xloc], sn_req, width=w, label="SN local REQ accept peak", color="#dc2626")
        ax.axhline(100, color="#64748b", ls="--", lw=1)
        ax.set_xticks(xloc)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("flit/cycle util (% of 1.0 link)")
        ax.set_title("At best lambda per row: SN inject/eject peak vs mesh E2E delivery")
        ax.legend(fontsize=8, loc="upper left")
        ax.set_ylim(0, 110)
        ax.grid(alpha=0.2, axis="y")

        axt = fig.add_axes([0.06, 0.12, 0.88, 0.34])
        axt.axis("off")
        header = ["mix", "buf", "lambda", "SN DAT peak", "SN DAT avg",
                  "E2E DAT util", "SN REQ peak", "SN REQ avg", "dat metric"]
        body = []
        for r in rows:
            body.append([
                r["mix"], r["vc_buf_size"], r["lambda"],
                f"{float(r['sn_dat_peak']):.3f}",
                f"{float(r['sn_dat_avg']):.3f}",
                f"{float(r['e2e_dat_util']):.1%}",
                f"{float(r['sn_req_peak']):.3f}",
                f"{float(r['sn_req_avg']):.3f}",
                r["dat_metric"],
            ])
        tbl = axt.table(cellText=[header] + body, loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        tbl.scale(1.0, 1.7)
        for c in range(len(header)):
            tbl[0, c].set_facecolor("#1e293b")
            tbl[0, c].set_text_props(color="white", fontweight="bold")

        notes = (
            "SN local DAT read  = max sent_flits/cycle at nodes 168-171 (CompData inject).\n"
            "SN local DAT write = max accepted_flits/cycle at SN (L3EvictData eject).\n"
            "SN local REQ       = max accepted_flits/cycle at SN for HN->SN request class.\n"
            "E2E DAT util       = sweep_sn_throughput metric (read: delivered to RN; write: to SN).\n\n"
            "If SN local DAT peak ~ E2E for write but SN local >> E2E for read, the gap is mesh "
            "fan-out after SN inject, not the SN terminal link itself."
        )
        fig.text(0.06, 0.06, notes, fontsize=8.5, va="top",
                 bbox=dict(boxstyle="round", fc="#f8fafc", ec="#cbd5e1"))
        fig.savefig(PNG_OUT, dpi=120)
        pdf.savefig(fig)
        plt.close(fig)

    print(f"Wrote {PDF_OUT}")
    print(f"Wrote {PNG_OUT}")


if __name__ == "__main__":
    main()
