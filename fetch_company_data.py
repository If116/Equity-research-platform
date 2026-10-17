"""
fetch_company_data.py

Pulls real financial data for ANY public ticker using yfinance and transforms
it into this platform's data/companies/<TICKER>.json schema -- the same shape
that NKE.json and LULU.json use, just populated automatically instead of by
hand from a 10-K.

IMPORTANT: this module makes live network calls. It was written and reviewed
for correctness against yfinance's documented API shape, but could NOT be
tested with a live call in the environment it was built in (no internet
access there). Run `python3 fetch_company_data.py TICKER` yourself the first
time you use it and sanity-check the output against a source like
stockanalysis.com before trusting it -- see the printed warnings for any
field it couldn't find.

WHY THIS DOESN'T AUTO-GENERATE A DCF THESIS: growth_path and the other
dcf_assumptions are deliberately written as a flat, clearly-labeled
PLACEHOLDER. TEACHING_GUIDE.md section 1 covers a real bug in an earlier
version of this platform caused by reusing one company's growth thesis for
another -- auto-generating a "thesis" here would just reintroduce that bug
one layer deeper. You write dcf_assumptions yourself; that's the actual
analytical work.
"""

import json
import sys
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _get_row(df, candidate_labels, col_index=0, default=0.0, warnings=None, field_name=""):
    """
    yfinance's row labels drift across versions/tickers (e.g. 'Net PPE' vs
    'Net Property Plant And Equipment'). Try each candidate label in order
    and return the first match at the given column; otherwise warn and
    fall back to `default` rather than crashing the whole fetch.
    """
    for label in candidate_labels:
        if label in df.index:
            try:
                val = df.loc[label].iloc[col_index]
                if val is not None and str(val) != "nan":
                    return float(val)
            except (IndexError, KeyError, ValueError, TypeError):
                continue
    if warnings is not None:
        warnings.append(f"Could not find any of {candidate_labels} for '{field_name}' -- defaulted to {default}")
    return default


def fetch_company(ticker, years=3):
    """
    Returns (data_dict, warnings_list). data_dict matches the schema in
    data/companies/_TEMPLATE.json. warnings_list flags every field that
    couldn't be found and had to be defaulted -- READ THESE, don't just
    trust a clean-looking JSON file.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError(
            "yfinance isn't installed. Run: pip install yfinance (see requirements.txt)"
        )

    warnings = []
    t = yf.Ticker(ticker)
    info = t.info

    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        raise ValueError(
            f"yfinance returned no usable data for '{ticker}'. Check the ticker is correct "
            f"and that you have an internet connection."
        )

    company_name = info.get("longName") or info.get("shortName") or ticker
    currency = info.get("currency", "USD")

    # --- Income statement (annual) ---
    financials = t.financials  # columns = fiscal years, most recent first
    if financials is None or financials.empty:
        raise ValueError(f"No income statement data returned for '{ticker}'.")

    fy_columns = list(financials.columns)[:years]
    fy_columns = sorted(fy_columns)  # oldest -> newest, matches NKE.json/LULU.json convention

    income_statement = {}
    for i, col in enumerate(fy_columns):
        col_idx = list(financials.columns).index(col)
        revenue = _get_row(financials, ["Total Revenue", "Operating Revenue"], col_idx, warnings=warnings, field_name=f"revenue ({col})")
        ebit = _get_row(financials, ["Operating Income", "EBIT"], col_idx, warnings=warnings, field_name=f"EBIT ({col})")
        net_income = _get_row(financials, ["Net Income", "Net Income Common Stockholders"], col_idx, warnings=warnings, field_name=f"net income ({col})")
        diluted_eps = _get_row(financials, ["Diluted EPS"], col_idx, default=None, warnings=warnings, field_name=f"diluted EPS ({col})")

        fy_label = f"FY{col.year}"
        entry = {
            "revenue": round(revenue / 1e6, 1),
            "ebit": round(ebit / 1e6, 1),
            "ebit_margin": round(ebit / revenue, 4) if revenue else None,
            "net_income": round(net_income / 1e6, 1),
        }
        if i == len(fy_columns) - 1 and diluted_eps:  # only the latest year needs diluted_eps
            entry["diluted_eps"] = round(diluted_eps, 2)
        income_statement[fy_label] = entry

    latest_fy = sorted(income_statement.keys())[-1]

    # --- Cash flow statement (annual) ---
    cashflow = t.cashflow
    cash_flow = {}
    if cashflow is not None and not cashflow.empty:
        for col in fy_columns:
            if col not in cashflow.columns:
                continue
            col_idx = list(cashflow.columns).index(col)
            fy_label = f"FY{col.year}"
            cfo = _get_row(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"], col_idx, warnings=warnings, field_name=f"CFO ({fy_label})")
            capex = _get_row(cashflow, ["Capital Expenditure", "Capital Expenditures"], col_idx, warnings=warnings, field_name=f"capex ({fy_label})")
            d_and_a = _get_row(cashflow, ["Depreciation And Amortization", "Depreciation"], col_idx, warnings=warnings, field_name=f"D&A ({fy_label})")
            cash_flow[fy_label] = {
                "cfo": round(cfo / 1e6, 1),
                "capex": round(capex / 1e6, 1),  # yfinance reports this as negative already
                "d_and_a": round(d_and_a / 1e6, 1),
                "fcf": round((cfo + capex) / 1e6, 1),
            }
    else:
        warnings.append("No cash flow statement returned at all -- cash_flow will be empty; fill in manually.")

    # --- Balance sheet (latest period only) ---
    balance_sheet = t.balance_sheet
    bs = {}
    if balance_sheet is not None and not balance_sheet.empty:
        col_idx = 0  # most recent period
        bs = {
            "cash_and_equivalents": round(_get_row(balance_sheet, ["Cash And Cash Equivalents", "Cash"], col_idx, warnings=warnings, field_name="cash") / 1e6, 1),
            "short_term_investments": round(_get_row(balance_sheet, ["Other Short Term Investments", "Short Term Investments"], col_idx, default=0.0, warnings=warnings, field_name="short-term investments") / 1e6, 1),
            "total_current_assets": round(_get_row(balance_sheet, ["Current Assets", "Total Current Assets"], col_idx, warnings=warnings, field_name="total current assets") / 1e6, 1),
            "pp_and_e_net": round(_get_row(balance_sheet, ["Net PPE", "Net Property Plant And Equipment"], col_idx, warnings=warnings, field_name="PP&E net") / 1e6, 1),
            "total_assets": round(_get_row(balance_sheet, ["Total Assets"], col_idx, warnings=warnings, field_name="total assets") / 1e6, 1),
            "total_current_liabilities": round(_get_row(balance_sheet, ["Current Liabilities", "Total Current Liabilities"], col_idx, warnings=warnings, field_name="total current liabilities") / 1e6, 1),
            "long_term_debt": round(_get_row(balance_sheet, ["Long Term Debt"], col_idx, default=0.0, warnings=warnings, field_name="long-term debt") / 1e6, 1),
            "operating_lease_liabilities": round(_get_row(balance_sheet, ["Long Term Lease Liabilities", "Operating Lease Liabilities"], col_idx, default=0.0, warnings=warnings, field_name="operating lease liabilities") / 1e6, 1),
            "notes_payable": round(_get_row(balance_sheet, ["Notes Payable", "Current Debt"], col_idx, default=0.0, warnings=warnings, field_name="notes payable") / 1e6, 1),
        }
        bs["total_debt"] = round(_get_row(balance_sheet, ["Total Debt"], col_idx, default=bs["long_term_debt"] + bs["notes_payable"], warnings=warnings, field_name="total debt") / 1e6, 1) \
            if "Total Debt" in balance_sheet.index else round(bs["long_term_debt"] + bs["notes_payable"], 1)
        total_liab = _get_row(balance_sheet, ["Total Liabilities Net Minority Interest", "Total Liab"], col_idx, warnings=warnings, field_name="total liabilities")
        known_liab = bs["total_current_liabilities"] + bs["long_term_debt"] + bs["operating_lease_liabilities"]
        bs["deferred_taxes_and_other_liabilities"] = round(max(total_liab / 1e6 - known_liab, 0), 1)
    else:
        warnings.append("No balance sheet returned at all -- balance_sheet_latest will be empty; fill in manually.")

    # --- Market data ---
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    market_data = {
        "as_of": date.today().isoformat(),
        "share_price": price,
        "market_cap": round(info.get("marketCap", 0) / 1e6, 1) if info.get("marketCap") else None,
        "diluted_shares_outstanding": round(info.get("sharesOutstanding", 0) / 1e6, 2) if info.get("sharesOutstanding") else None,
        "ttm_eps": info.get("trailingEps"),
        "ttm_pe": info.get("trailingPE"),
        "52wk_low": info.get("fiftyTwoWeekLow"),
        "52wk_high": info.get("fiftyTwoWeekHigh"),
        "beta": info.get("beta", 1.0),
    }
    for k, v in market_data.items():
        if v is None and k != "as_of":
            warnings.append(f"market_data.{k} was not available from yfinance -- fill in manually.")

    data = {
        "company": company_name,
        "ticker": ticker.upper(),
        "fiscal_year_end": "auto-detected from yfinance fiscal year columns -- verify against the 10-K cover page",
        "as_of_date": date.today().isoformat(),
        "currency": f"{currency} millions (except per-share and price data)",
        "sources": [f"yfinance (Yahoo Finance), fetched {date.today().isoformat()}"],
        "notes": (
            "AUTO-FETCHED via fetch_company_data.py -- NOT manually verified against a 10-K. "
            "Review every field, especially cash_flow and balance_sheet_latest, before relying on this. "
            + (f"{len(warnings)} field(s) could not be found and were defaulted -- see warnings." if warnings else "")
        ),
        "latest_fiscal_year": latest_fy,
        "peers": [],
        "income_statement": income_statement,
        "cash_flow": cash_flow,
        "balance_sheet_latest": bs,
        "dcf_assumptions": {
            "note": (
                "PLACEHOLDER -- auto-generated flat 3% growth assumption. This is NOT a real thesis. "
                "Replace growth_path and this note with your own view of the company's trajectory "
                "before trusting the DCF output. See TEACHING_GUIDE.md section 1."
            ),
            "risk_free_rate": 0.042,
            "equity_risk_premium": 0.05,
            "pre_tax_cost_of_debt": 0.05,
            "tax_rate": 0.22,
            "terminal_growth": 0.025,
            "growth_path": [0.03, 0.03, 0.03, 0.03, 0.03],
        },
        "market_data": market_data,
    }
    return data, warnings


def fetch_peer_profile(ticker):
    """Minimal profile for the peer_universe.json pool: market cap, revenue, P/E, EV/EBITDA."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    info = t.info
    ev_ebitda = None
    if info.get("enterpriseValue") and info.get("ebitda"):
        ev_ebitda = round(info["enterpriseValue"] / info["ebitda"], 2)
    return {
        "ticker": ticker.upper(),
        "name": info.get("longName") or info.get("shortName") or ticker,
        "market_cap": round(info.get("marketCap", 0) / 1e6, 1) if info.get("marketCap") else None,
        "ttm_revenue": round(info.get("totalRevenue", 0) / 1e6, 1) if info.get("totalRevenue") else None,
        "gross_margin": info.get("grossMargins"),
        "ebitda_margin": info.get("ebitdaMargins"),
        "pe_ratio": info.get("trailingPE"),
        "ev_ebitda": ev_ebitda,
    }


def save_company(ticker, data, force=False):
    path = DATA_DIR / "companies" / f"{ticker.upper()}.json"
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists. Pass force=True / --force to overwrite.")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch real financial data for a ticker and build its company JSON file.")
    parser.add_argument("ticker")
    parser.add_argument("--force", action="store_true", help="overwrite an existing data/companies/<TICKER>.json")
    args = parser.parse_args()

    print(f"Fetching {args.ticker}...")
    data, warnings = fetch_company(args.ticker)

    if warnings:
        print(f"\n{len(warnings)} WARNING(S) -- review before trusting this data:")
        for w in warnings:
            print(f"  - {w}")

    path = save_company(args.ticker, data, force=args.force)
    print(f"\nWrote {path}")
    print("Next steps:")
    print(f"  1. Open {path} and fix anything flagged above, plus add a real 'peers' list and 'dcf_assumptions'.")
    print(f"  2. python3 analysis.py {args.ticker.upper()}")
    print(f"  3. python3 generate_report.py {args.ticker.upper()}")
