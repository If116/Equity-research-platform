"""
financials.py

Loads a target company's financial data (from data/companies/<TICKER>.json)
and computes the core operating, profitability, and credit metrics:
revenue growth, EBITDA / EBITDA margin, FCF margin, ROIC, and leverage.

This file is company-agnostic: swap the ticker and every function below
works unchanged, as long as the company's JSON file follows the same shape
as data/companies/NKE.json (see data/companies/_TEMPLATE.json).
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
ASSUMED_TAX_RATE = 0.22  # blended effective tax rate assumption, see valuation.py


def load_financials(ticker="NKE"):
    path = DATA_DIR / "companies" / f"{ticker}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No data file for '{ticker}' at {path}. "
            f"Copy data/companies/_TEMPLATE.json to {path.name} and fill it in."
        )
    with open(path) as f:
        return json.load(f)


def latest_year(data):
    """The company's most recent fiscal year, as declared in its own data file."""
    return data["latest_fiscal_year"]


def revenue_growth(data):
    """Year-over-year revenue growth for each fiscal year with a prior-year comp."""
    inc = data["income_statement"]
    years = sorted(inc.keys())
    return {
        curr: (inc[curr]["revenue"] - inc[prev]["revenue"]) / inc[prev]["revenue"]
        for prev, curr in zip(years, years[1:])
    }


def ebitda_by_year(data):
    """EBITDA = EBIT + D&A, matched by fiscal year."""
    inc, cf = data["income_statement"], data["cash_flow"]
    return {y: inc[y]["ebit"] + cf[y]["d_and_a"] for y in inc if y in cf}


def ebitda_margin_by_year(data):
    inc = data["income_statement"]
    ebitda = ebitda_by_year(data)
    return {y: ebitda[y] / inc[y]["revenue"] for y in ebitda}


def fcf_margin_by_year(data):
    inc, cf = data["income_statement"], data["cash_flow"]
    return {y: cf[y]["fcf"] / inc[y]["revenue"] for y in inc if y in cf}


def net_income_margin_by_year(data):
    inc = data["income_statement"]
    return {y: v["net_income"] / v["revenue"] for y, v in inc.items()}


def roic(data, year=None, tax_rate=ASSUMED_TAX_RATE):
    """
    ROIC = NOPAT / Invested Capital
    NOPAT = EBIT * (1 - tax rate)
    Invested Capital = Total Debt + Equity - Cash & Equivalents
    Equity is backed into from disclosed balance-sheet lines (Assets - Liabilities).
    """
    year = year or latest_year(data)
    inc = data["income_statement"][year]
    bs = data["balance_sheet_latest"]

    nopat = inc["ebit"] * (1 - tax_rate)

    total_liabilities = (
        bs["total_current_liabilities"]
        + bs["long_term_debt"]
        + bs["operating_lease_liabilities"]
        + bs["deferred_taxes_and_other_liabilities"]
    )
    equity = bs["total_assets"] - total_liabilities
    invested_capital = bs["total_debt"] + equity - bs["cash_and_equivalents"]

    return nopat / invested_capital


def leverage_ratios(data, year=None):
    """Net debt / EBITDA and Total debt / EBITDA -- standard credit-risk leverage metrics."""
    year = year or latest_year(data)
    bs = data["balance_sheet_latest"]
    ebitda = ebitda_by_year(data)[year]
    net_debt = bs["total_debt"] - bs["cash_and_equivalents"] - bs["short_term_investments"]
    return {
        "net_debt": net_debt,
        "net_debt_to_ebitda": net_debt / ebitda,
        "total_debt_to_ebitda": bs["total_debt"] / ebitda,
    }


def summary_table(data):
    """One consolidated dict of every metric above, keyed by fiscal year -- feeds analysis.py/dashboard."""
    years = sorted(data["income_statement"].keys())
    growth = revenue_growth(data)
    ebitda = ebitda_by_year(data)
    ebitda_m = ebitda_margin_by_year(data)
    fcf_m = fcf_margin_by_year(data)
    ni_m = net_income_margin_by_year(data)

    rows = []
    for y in years:
        rows.append({
            "fiscal_year": y,
            "revenue": data["income_statement"][y]["revenue"],
            "revenue_growth": growth.get(y),
            "ebit": data["income_statement"][y]["ebit"],
            "ebit_margin": data["income_statement"][y]["ebit_margin"],
            "ebitda": ebitda.get(y),
            "ebitda_margin": ebitda_m.get(y),
            "net_income": data["income_statement"][y]["net_income"],
            "net_income_margin": ni_m.get(y),
            "fcf": data["cash_flow"].get(y, {}).get("fcf"),
            "fcf_margin": fcf_m.get(y),
        })
    return rows


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NKE"
    data = load_financials(ticker)
    for row in summary_table(data):
        print(row)
    print(f"\nROIC ({latest_year(data)}):", round(roic(data) * 100, 2), "%")
    print("Leverage:", leverage_ratios(data))
