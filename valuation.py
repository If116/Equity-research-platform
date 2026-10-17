"""
valuation.py

Builds a standard unlevered DCF for whatever company financials.py loaded:
  1. WACC via CAPM (cost of equity) blended with after-tax cost of debt
  2. 5-year explicit FCF projection off a base-year FCF and a growth path
  3. Gordon Growth terminal value
  4. Enterprise Value -> Equity Value -> implied share price
  5. A WACC x terminal-growth sensitivity grid (the standard "DCF football field" input)

Every assumption below is a DEFAULT ONLY. The real, company-specific values
come from an optional "dcf_assumptions" block in that company's own
data/companies/<TICKER>.json -- because reusing one company's growth
narrative to value a different company is exactly the kind of mistake this
file is built to make impossible to do by accident. Compare data/companies/
NKE.json (a post-trough "recovery" thesis) with LULU.json (a "guidance was
just cut -- model a near-term reset" thesis) to see this in practice.
"""

from financials import load_financials, latest_year

# ---- Fallback assumptions, used only if a company's JSON doesn't specify its own ----
DEFAULT_RISK_FREE_RATE = 0.042      # ~current 10-year Treasury yield assumption
DEFAULT_EQUITY_RISK_PREMIUM = 0.05  # long-run US equity risk premium assumption
DEFAULT_PRE_TAX_COST_OF_DEBT = 0.05 # approx. investment-grade coupon-level cost
DEFAULT_TAX_RATE = 0.22             # blended effective tax rate assumption
DEFAULT_TERMINAL_GROWTH = 0.025     # long-run terminal growth (~long-run nominal GDP)
DEFAULT_GROWTH_PATH = [0.03, 0.03, 0.03, 0.03, 0.03]  # flat 3% if a company states no thesis


def assumptions(data):
    """
    Pulls DCF assumptions from the company's own file (data["dcf_assumptions"]),
    falling back to the module defaults for anything it doesn't specify.
    """
    a = data.get("dcf_assumptions", {})
    return {
        "risk_free_rate": a.get("risk_free_rate", DEFAULT_RISK_FREE_RATE),
        "equity_risk_premium": a.get("equity_risk_premium", DEFAULT_EQUITY_RISK_PREMIUM),
        "pre_tax_cost_of_debt": a.get("pre_tax_cost_of_debt", DEFAULT_PRE_TAX_COST_OF_DEBT),
        "tax_rate": a.get("tax_rate", DEFAULT_TAX_RATE),
        "terminal_growth": a.get("terminal_growth", DEFAULT_TERMINAL_GROWTH),
        "growth_path": a.get("growth_path", DEFAULT_GROWTH_PATH),
    }


def cost_of_equity(beta, rf, erp):
    """CAPM: Re = Rf + Beta * ERP"""
    return rf + beta * erp


def wacc(data):
    mkt = data["market_data"]
    bs = data["balance_sheet_latest"]
    a = assumptions(data)

    E = mkt["market_cap"]
    D = bs["total_debt"]
    V = E + D

    re = cost_of_equity(mkt["beta"], a["risk_free_rate"], a["equity_risk_premium"])
    rd_after_tax = a["pre_tax_cost_of_debt"] * (1 - a["tax_rate"])

    # All-equity companies (e.g. LULU carries ~$0 funded debt) collapse to WACC = cost of equity.
    w = (E / V) * re + (D / V) * rd_after_tax if V else re
    return {"wacc": w, "cost_of_equity": re, "cost_of_debt_after_tax": rd_after_tax,
            "weight_equity": E / V if V else 1.0, "weight_debt": D / V if V else 0.0}


def project_fcf(base_fcf, growth_path):
    """Explicit-period FCF projection off a base-year figure and a growth path."""
    projections = []
    fcf = base_fcf
    for g in growth_path:
        fcf = fcf * (1 + g)
        projections.append(fcf)
    return projections


def dcf_valuation(data, discount_rate=None, terminal_growth=None, growth_path=None):
    """
    Returns enterprise value, equity value, and implied share price for a given
    WACC and terminal growth rate. Any of discount_rate/terminal_growth/growth_path
    left as None fall back to the company's own dcf_assumptions (or the module
    defaults) -- pass explicit values to override them, e.g. for a sensitivity grid.
    """
    a = assumptions(data)
    r = discount_rate if discount_rate is not None else wacc(data)["wacc"]
    g_terminal = terminal_growth if terminal_growth is not None else a["terminal_growth"]
    g_path = growth_path if growth_path is not None else a["growth_path"]

    base_fcf = data["cash_flow"][latest_year(data)]["fcf"]
    fcfs = project_fcf(base_fcf, g_path)
    pv_fcfs = [fcf / (1 + r) ** (i + 1) for i, fcf in enumerate(fcfs)]

    terminal_value = fcfs[-1] * (1 + g_terminal) / (r - g_terminal)
    pv_terminal_value = terminal_value / (1 + r) ** len(fcfs)

    enterprise_value = sum(pv_fcfs) + pv_terminal_value

    bs = data["balance_sheet_latest"]
    equity_value = enterprise_value - bs["total_debt"] + bs["cash_and_equivalents"]
    shares = data["market_data"]["diluted_shares_outstanding"]
    implied_price = equity_value / shares

    return {
        "wacc_used": r,
        "terminal_growth_used": g_terminal,
        "growth_path_used": g_path,
        "projected_fcfs": fcfs,
        "pv_fcfs": pv_fcfs,
        "terminal_value": terminal_value,
        "pv_terminal_value": pv_terminal_value,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "implied_share_price": implied_price,
    }


def sensitivity_grid(data, wacc_range=None, growth_range=None):
    """
    Builds the classic DCF sensitivity table: implied share price across a
    grid of WACC (rows) x terminal growth rate (columns). Growth PATH (the
    5-year explicit projection) stays fixed at the company's own assumption --
    only WACC and terminal growth vary, matching standard practice.
    """
    base_wacc = wacc(data)["wacc"]
    if wacc_range is None:
        wacc_range = [round(base_wacc + delta, 4) for delta in (-0.01, -0.005, 0, 0.005, 0.01)]
    if growth_range is None:
        growth_range = [0.015, 0.02, 0.025, 0.03, 0.035]

    grid = {}
    for w in wacc_range:
        row = {}
        for g in growth_range:
            if w <= g:
                row[g] = None  # WACC must exceed terminal growth or the model breaks
                continue
            row[g] = round(dcf_valuation(data, discount_rate=w, terminal_growth=g)["implied_share_price"], 2)
        grid[w] = row
    return grid


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NKE"
    data = load_financials(ticker)
    w = wacc(data)
    print("WACC build-up:", {k: round(v, 4) for k, v in w.items()})

    result = dcf_valuation(data)
    print("\nDCF result:")
    for k, v in result.items():
        if isinstance(v, list):
            print(f"  {k}: {[round(x, 3) if isinstance(x, float) and abs(x) < 1 else round(x) for x in v]}")
        else:
            print(f"  {k}: {round(v, 4) if isinstance(v, float) else v}")

    print(f"\nCurrent share price: ${data['market_data']['share_price']}")
    print(f"Implied DCF share price: ${round(result['implied_share_price'], 2)}")

    print("\nSensitivity grid (rows = WACC, cols = terminal growth):")
    grid = sensitivity_grid(data)
    for w_val, row in grid.items():
        print(f"  WACC {round(w_val*100,2)}%: ", {f"{round(g*100,1)}%": v for g, v in row.items()})
