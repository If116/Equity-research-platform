"""
analysis.py

Orchestrates the full pipeline for a given ticker:
  financials.py -> comps.py -> valuation.py -> charts/<TICKER>/ + data/output_<TICKER>.json

Usage:
    python3 analysis.py            # defaults to NKE
    python3 analysis.py LULU       # runs the whole pipeline for any company with a
                                     data/companies/LULU.json file
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import financials as fin
import comps
import valuation as val

BASE = Path(__file__).parent
NAVY = "#1f2937"
ORANGE = "#f97316"
GRAY = "#9ca3af"


def chart_revenue_and_margin(summary, ticker, chart_dir, company_name):
    years = [r["fiscal_year"] for r in summary]
    revenue = [r["revenue"] / 1000 for r in summary]
    ebit_margin = [r["ebit_margin"] * 100 for r in summary]

    fig, ax1 = plt.subplots(figsize=(7, 4.2))
    ax1.bar(years, revenue, color=NAVY, width=0.5, label="Revenue ($B)")
    ax1.set_ylabel("Revenue ($B)")
    ax1.set_ylim(0, max(revenue) * 1.25)
    for i, v in enumerate(revenue):
        ax1.text(i, v + max(revenue) * 0.02, f"${v:.1f}B", ha="center", fontsize=9)

    ax2 = ax1.twinx()
    ax2.plot(years, ebit_margin, color=ORANGE, marker="o", linewidth=2, label="EBIT margin")
    ax2.set_ylabel("EBIT margin (%)")
    ax2.set_ylim(0, max(ebit_margin) * 1.6)
    for i, v in enumerate(ebit_margin):
        ax2.text(i, v + max(ebit_margin) * 0.03, f"{v:.1f}%", ha="center", fontsize=9, color=ORANGE)

    plt.title(f"{company_name} — Revenue & EBIT Margin ({years[0]}–{years[-1]})")
    fig.tight_layout()
    fig.savefig(chart_dir / "revenue_margin.png", dpi=150)
    plt.close(fig)


def chart_fcf(summary, ticker, chart_dir, company_name):
    years = [r["fiscal_year"] for r in summary]
    fcf = [r["fcf"] / 1000 for r in summary]

    fig, ax = plt.subplots(figsize=(7, 4.2))
    colors = [NAVY if v >= 0 else "#b91c1c" for v in fcf]
    ax.bar(years, fcf, color=colors, width=0.5)
    for i, v in enumerate(fcf):
        ax.text(i, v + abs(max(fcf)) * 0.02, f"${v:.2f}B", ha="center", fontsize=9)
    ax.set_ylabel("Free Cash Flow ($B)")
    ax.set_title(f"{company_name} — Free Cash Flow ({years[0]}–{years[-1]})")
    fig.tight_layout()
    fig.savefig(chart_dir / "fcf.png", dpi=150)
    plt.close(fig)


def chart_comps(comps_rows, ticker, chart_dir):
    labels = [r["ticker"] for r in comps_rows]
    ev_ebitda = [r["ev_ebitda"] if r["ev_ebitda"] else 0 for r in comps_rows]
    colors = [ORANGE if t == ticker else GRAY for t in labels]

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.bar(labels, ev_ebitda, color=colors)
    for i, v in enumerate(ev_ebitda):
        if v:
            ax.text(i, v + 0.15, f"{v:.1f}x", ha="center", fontsize=9)
    ax.set_ylabel("EV / EBITDA")
    ax.set_title("Peer Comps — EV/EBITDA Multiples")
    fig.tight_layout()
    fig.savefig(chart_dir / "comps_ev_ebitda.png", dpi=150)
    plt.close(fig)


def chart_dcf_bridge(dcf_result, current_price, chart_dir):
    labels = ["Current\nPrice", "DCF Implied\nPrice"]
    values = [current_price, dcf_result["implied_share_price"]]
    colors = [GRAY, ORANGE]

    fig, ax = plt.subplots(figsize=(5, 4.2))
    ax.bar(labels, values, color=colors, width=0.5)
    for i, v in enumerate(values):
        ax.text(i, v + max(values) * 0.02, f"${v:.2f}", ha="center", fontsize=10)
    ax.set_ylabel("Price per share ($)")
    ax.set_title("DCF: Implied vs. Current Share Price")
    fig.tight_layout()
    fig.savefig(chart_dir / "dcf_bridge.png", dpi=150)
    plt.close(fig)


def run(ticker="NKE"):
    data = fin.load_financials(ticker)
    peers = comps.load_peers(data)

    chart_dir = BASE / "charts" / ticker
    chart_dir.mkdir(parents=True, exist_ok=True)

    summary = fin.summary_table(data)
    roic = fin.roic(data)
    leverage = fin.leverage_ratios(data)

    peer_avg = comps.peer_average_multiples(peers)
    target_mult = comps.target_multiples(data)
    implied_comps = comps.implied_valuation_from_comps(data, peers)
    comps_rows = comps.comps_table(data, peers)

    wacc_build = val.wacc(data)
    dcf_result = val.dcf_valuation(data)
    sensitivity = val.sensitivity_grid(data)

    chart_revenue_and_margin(summary, ticker, chart_dir, data["company"])
    chart_fcf(summary, ticker, chart_dir, data["company"])
    chart_comps(comps_rows, ticker, chart_dir)
    chart_dcf_bridge(dcf_result, data["market_data"]["share_price"], chart_dir)

    output = {
        "company": data["company"],
        "ticker": data["ticker"],
        "as_of_date": data["as_of_date"],
        "current_price": data["market_data"]["share_price"],
        "peers": data.get("peers", []),
        "dcf_note": data.get("dcf_assumptions", {}).get("note"),
        "financial_summary": summary,
        "roic": roic,
        "leverage": leverage,
        "peer_avg_multiples": peer_avg,
        "target_multiples": target_mult,
        "comps_table": comps_rows,
        "implied_valuation_comps": implied_comps,
        "wacc_buildup": wacc_build,
        "dcf_result": dict(dcf_result),
        "sensitivity_grid": {str(round(w * 100, 2)) + "%": {str(round(g * 100, 1)) + "%": v
                              for g, v in row.items()} for w, row in sensitivity.items()},
    }

    out_path = BASE / "data" / f"output_{ticker}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=float)

    print(f"Charts written to {chart_dir}")
    print(f"Consolidated output written to {out_path}")
    return output


if __name__ == "__main__":
    ticker_arg = sys.argv[1] if len(sys.argv) > 1 else "NKE"
    run(ticker_arg)
