"""
generate_report.py

Assembles charts/ + data/output.json into a formatted equity research PDF,
research_report.pdf, using reportlab.
"""

import json
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, HRFlowable
)

BASE = Path(__file__).parent

NAVY = colors.HexColor("#1f2937")
ORANGE = colors.HexColor("#f97316")


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", fontSize=20, leading=24, textColor=NAVY,
                               spaceAfter=4, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="ReportSubtitle", fontSize=12, leading=15, textColor=colors.gray,
                               spaceAfter=14))
    styles.add(ParagraphStyle(name="SectionHeader", fontSize=14, leading=18, textColor=NAVY,
                               spaceBefore=14, spaceAfter=8, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Body", fontSize=10, leading=14, spaceAfter=8))
    styles.add(ParagraphStyle(name="Caption", fontSize=8, leading=10, textColor=colors.gray))
    return styles


def data_table(rows, header, col_widths=None):
    t = Table([header] + rows, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def describe_financial_trend(d):
    """Auto-generates the Section 1 narrative from the actual data -- no company-specific hardcoding."""
    summary = d["financial_summary"]
    first, last = summary[0], summary[-1]
    rev_change = (last["revenue"] - first["revenue"]) / first["revenue"] * 100
    rev_direction = "grew" if rev_change > 0 else "declined"
    margin_change = (last["ebit_margin"] - first["ebit_margin"]) * 100

    margin_desc = (
        f"expanded {margin_change:.1f} points" if margin_change > 0
        else f"compressed {abs(margin_change):.1f} points" if margin_change < 0
        else "held roughly steady"
    )

    return (
        f"{d['company']}'s revenue {rev_direction} {abs(rev_change):.1f}% from "
        f"{first['fiscal_year']} (${first['revenue']:,}M) to {last['fiscal_year']} "
        f"(${last['revenue']:,}M). Over the same period, EBIT margin {margin_desc}, from "
        f"{first['ebit_margin']*100:.1f}% to {last['ebit_margin']*100:.1f}%."
    )


def describe_comps(d):
    """Auto-generates the Section 2 narrative -- peer list and implied-vs-current framing."""
    peers = [r["ticker"] for r in d["comps_table"] if r["ticker"] != d["ticker"]]
    peer_str = ", ".join(peers[:-1]) + (f", and {peers[-1]}" if len(peers) > 1 else peers[0] if peers else "")

    implied_ev = d["implied_valuation_comps"]["implied_share_price_ev_ebitda"]
    implied_pe = d["implied_valuation_comps"]["implied_share_price_pe"]
    current = d["current_price"]
    target_ev_ebitda = d["target_multiples"]["ev_ebitda"]
    peer_avg_ev_ebitda = d["peer_avg_multiples"]["avg_ev_ebitda"]

    premium_discount = "a premium to" if target_ev_ebitda > peer_avg_ev_ebitda else "a discount to"

    intro = f"{d['ticker']} is benchmarked against public peers in the same sector: {peer_str}."

    ev_line = (
        f"Applying the peer-average EV/EBITDA multiple ({peer_avg_ev_ebitda:.1f}x) to {d['ticker']}'s "
        f"latest-year EBITDA implies a share price of ${implied_ev:.2f} — "
        f"{'below' if implied_ev < current else 'above'} the current price of ${current:.2f}, since "
        f"{d['ticker']} trades at {premium_discount} peers ({target_ev_ebitda:.1f}x vs. {peer_avg_ev_ebitda:.1f}x)."
        if implied_ev else
        "Peer EV/EBITDA data was too sparse to derive an implied price from this approach."
    )
    pe_line = (
        f" The peer-average P/E ({d['peer_avg_multiples']['avg_pe']:.1f}x) applied to trailing EPS implies "
        f"${implied_pe:.2f}, {'below' if implied_pe < current else 'above'} the current price — "
        f"the gap between the two approaches is itself worth interrogating: EBITDA and EPS multiples "
        f"can point in different directions when leverage, D&amp;A, or one-off items move between the two."
        if implied_pe else ""
    )
    return intro + " " + ev_line + pe_line


def describe_dcf(d):
    """Auto-generates the Section 3 narrative, including any company-specific thesis note."""
    dcf = d["dcf_result"]
    base = (
        f"Enterprise Value = PV(explicit FCFs) + PV(Terminal Value). Using a base-year FCF of "
        f"${d['financial_summary'][-1]['fcf']:,}M, a WACC of {dcf['wacc_used']*100:.2f}%, and a "
        f"terminal growth rate of {dcf['terminal_growth_used']*100:.1f}%, the model implies an "
        f"enterprise value of ${dcf['enterprise_value']:,.0f}M and an equity value of "
        f"${dcf['equity_value']:,.0f}M (${dcf['implied_share_price']:.2f} per share)."
    )
    if d.get("dcf_note"):
        base += f" <i>Growth assumption:</i> {d['dcf_note']}"
    return base


def describe_summary(d):
    """Auto-generates the closing summary by comparing all three implied valuations to the market price."""
    current = d["current_price"]
    approaches = {
        "DCF": d["dcf_result"]["implied_share_price"],
        "Comps (EV/EBITDA)": d["implied_valuation_comps"]["implied_share_price_ev_ebitda"],
        "Comps (P/E)": d["implied_valuation_comps"]["implied_share_price_pe"],
    }
    above = [k for k, v in approaches.items() if v and v > current]
    below = [k for k, v in approaches.items() if v and v <= current]

    spread_pct = (max(v for v in approaches.values() if v) / min(v for v in approaches.values() if v) - 1) * 100

    return (
        f"Across the three approaches, implied value ranges from "
        f"${min(v for v in approaches.values() if v):.2f} to ${max(v for v in approaches.values() if v):.2f} "
        f"per share — a spread of {spread_pct:.0f}%. "
        f"{', '.join(above) if above else 'No approach'} "
        f"{'imply' if len(above) != 1 else 'implies'} upside to the ${current:.2f} current price"
        f"{'; ' if above and below else '. '}"
        + (f"{', '.join(below)} {'imply' if len(below) != 1 else 'implies'} the stock is fairly "
           f"valued or overvalued today. " if below else "")
        + "That spread — not any single number — is the actual investment debate: each method leans on "
          "a different assumption (a growth/discount-rate thesis for the DCF, a peer set for comps), and "
          "defending which one you trust most is the real analytical work."
    )


def build_report(ticker="NKE"):
    chart_dir = BASE / "charts" / ticker
    out_path = BASE / f"research_report_{ticker}.pdf"

    with open(BASE / "data" / f"output_{ticker}.json") as f:
        d = json.load(f)

    styles = build_styles()
    story = []

    # --- Cover / header ---
    story.append(Paragraph(f"{d['company']} ({d['ticker']})", styles["ReportTitle"]))
    story.append(Paragraph("Equity Research &amp; Valuation Report", styles["ReportSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY))
    story.append(Spacer(1, 10))

    meta = [
        ["Current Price", f"${d['current_price']:.2f}"],
        ["As-of Date", d["as_of_date"]],
        ["DCF Implied Price", f"${d['dcf_result']['implied_share_price']:.2f}"],
        ["Comps (EV/EBITDA) Implied Price", f"${d['implied_valuation_comps']['implied_share_price_ev_ebitda']:.2f}"],
        ["Comps (P/E) Implied Price", f"${d['implied_valuation_comps']['implied_share_price_pe']:.2f}"],
    ]
    story.append(data_table(meta, ["Metric", "Value"], col_widths=[3 * inch, 2 * inch]))
    story.append(Spacer(1, 16))

    # --- Section 1: Business & Financial Overview ---
    story.append(Paragraph("1. Financial Overview", styles["SectionHeader"]))
    story.append(Paragraph(describe_financial_trend(d), styles["Body"]))
    story.append(Image(str(chart_dir / "revenue_margin.png"), width=6 * inch, height=3.6 * inch))
    story.append(Spacer(1, 6))

    fin_rows = [
        [r["fiscal_year"], f"${r['revenue']:,}", f"{r['ebit_margin']*100:.1f}%",
         f"{r['ebitda_margin']*100:.1f}%" if r["ebitda_margin"] else "n/a",
         f"{r['net_income_margin']*100:.1f}%"]
        for r in d["financial_summary"]
    ]
    story.append(data_table(
        fin_rows,
        ["Fiscal Year", "Revenue ($M)", "EBIT Margin", "EBITDA Margin", "Net Margin"],
        col_widths=[1.1 * inch, 1.3 * inch, 1.2 * inch, 1.3 * inch, 1.1 * inch]
    ))
    story.append(Spacer(1, 10))
    latest_fy = d["financial_summary"][-1]["fiscal_year"]
    story.append(Paragraph(
        f"<b>ROIC ({latest_fy}):</b> {d['roic']*100:.1f}%  |  "
        f"<b>Net Debt / EBITDA:</b> {d['leverage']['net_debt_to_ebitda']:.2f}x  |  "
        f"<b>Total Debt / EBITDA:</b> {d['leverage']['total_debt_to_ebitda']:.2f}x",
        styles["Body"]))

    story.append(Paragraph("Free Cash Flow", styles["SectionHeader"]))
    story.append(Image(str(chart_dir / "fcf.png"), width=6 * inch, height=3.6 * inch))
    story.append(PageBreak())

    # --- Section 2: Comparable Company Analysis ---
    story.append(Paragraph("2. Comparable Company Analysis", styles["SectionHeader"]))

    comps_rows = [
        [r["ticker"], f"${r['market_cap']:,}",
         f"${r['revenue']:,}" if r["revenue"] else "n/a",
         f"{r['pe']:.1f}x" if r["pe"] else "n/a",
         f"{r['ev_ebitda']:.1f}x" if r["ev_ebitda"] else "n/a"]
        for r in d["comps_table"]
    ]
    story.append(data_table(
        comps_rows,
        ["Ticker", "Mkt Cap ($M)", "Revenue ($M)", "P/E", "EV/EBITDA"],
        col_widths=[0.8 * inch, 1.3 * inch, 1.3 * inch, 0.9 * inch, 1.2 * inch]
    ))
    story.append(Spacer(1, 10))
    story.append(Image(str(chart_dir / "comps_ev_ebitda.png"), width=6 * inch, height=3.6 * inch))
    story.append(Spacer(1, 10))
    story.append(Paragraph(describe_comps(d), styles["Body"]))
    story.append(PageBreak())

    # --- Section 3: DCF Valuation ---
    story.append(Paragraph("3. Discounted Cash Flow Valuation", styles["SectionHeader"]))
    wacc_rows = [
        ["Cost of Equity (CAPM)", f"{d['wacc_buildup']['cost_of_equity']*100:.2f}%"],
        ["After-tax Cost of Debt", f"{d['wacc_buildup']['cost_of_debt_after_tax']*100:.2f}%"],
        ["Weight of Equity", f"{d['wacc_buildup']['weight_equity']*100:.1f}%"],
        ["Weight of Debt", f"{d['wacc_buildup']['weight_debt']*100:.1f}%"],
        ["WACC", f"{d['wacc_buildup']['wacc']*100:.2f}%"],
    ]
    story.append(data_table(wacc_rows, ["WACC Build-Up", "Value"], col_widths=[3 * inch, 2 * inch]))
    story.append(Spacer(1, 10))

    story.append(Paragraph(describe_dcf(d), styles["Body"]))
    story.append(Image(str(chart_dir / "dcf_bridge.png"), width=5 * inch, height=3.6 * inch))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Sensitivity: Implied Share Price (WACC x Terminal Growth)", styles["Body"]))
    grid = d["sensitivity_grid"]
    growth_cols = list(next(iter(grid.values())).keys())
    header = ["WACC \\ g"] + growth_cols
    sens_rows = []
    for wacc_key, row in grid.items():
        sens_rows.append([wacc_key] + [f"${v:.2f}" if v else "n/a" for v in row.values()])
    story.append(data_table(sens_rows, header,
                             col_widths=[0.9 * inch] + [0.85 * inch] * len(growth_cols)))
    story.append(Spacer(1, 14))

    # --- Section 4: Investment Conclusion ---
    story.append(Paragraph("4. Summary", styles["SectionHeader"]))
    story.append(Paragraph(describe_summary(d), styles["Body"]))
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray))
    story.append(Paragraph(
        "This report was built as an independent educational/portfolio project using public "
        "SEC filings and market data aggregators. It is not investment research and should not "
        "be relied upon for investment decisions. All models and assumptions are documented in "
        "the accompanying source code.",
        styles["Caption"]))

    doc = SimpleDocTemplate(str(out_path), pagesize=letter,
                             topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                             leftMargin=0.7 * inch, rightMargin=0.7 * inch)
    doc.build(story)
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    import sys
    ticker_arg = sys.argv[1] if len(sys.argv) > 1 else "NKE"
    build_report(ticker_arg)
