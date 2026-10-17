"""
comps.py

Builds the trading-comps table for whatever target company financials.py
loaded, and derives an implied valuation by applying peer-average multiples
to that company's own EBITDA and earnings.

Peers are looked up from data/peer_universe.json using the tickers listed
in the target company's own "peers" field -- add a new company's profile to
the universe once, and any other company's config can reference it as a peer.
"""

import json
from pathlib import Path
from statistics import mean

from financials import ebitda_by_year, latest_year

DATA_DIR = Path(__file__).parent / "data"


def load_universe():
    with open(DATA_DIR / "peer_universe.json") as f:
        return json.load(f)["companies"]


def load_peers(data):
    """Resolve the target company's declared peer tickers against the universe."""
    universe = {c["ticker"]: c for c in load_universe()}
    tickers = data.get("peers", [])
    missing = [t for t in tickers if t not in universe]
    if missing:
        raise KeyError(
            f"Peer(s) {missing} not found in data/peer_universe.json -- "
            f"add their profile there first."
        )
    return [universe[t] for t in tickers]


def peer_average_multiples(peers):
    """Simple average of each multiple across peers, ignoring missing (None) values."""
    ev_ebitda = [p["ev_ebitda"] for p in peers if p.get("ev_ebitda")]
    pe = [p["pe_ratio"] for p in peers if p.get("pe_ratio")]
    return {
        "avg_ev_ebitda": mean(ev_ebitda) if ev_ebitda else None,
        "avg_pe": mean(pe) if pe else None,
    }


def target_multiples(data):
    """The target company's own current trading multiples, for context alongside peers."""
    mkt = data["market_data"]
    year = latest_year(data)
    ebitda = ebitda_by_year(data)[year]
    bs = data["balance_sheet_latest"]
    ev = mkt["market_cap"] + bs["total_debt"] - bs["cash_and_equivalents"]
    return {
        "pe": mkt["ttm_pe"],
        "ev_ebitda": ev / ebitda,
        "enterprise_value": ev,
    }


def implied_valuation_from_comps(data, peers):
    """
    Apply peer-average EV/EBITDA and P/E multiples to the target's own latest-year
    EBITDA and TTM EPS to back into an implied enterprise value and share price.
    """
    avg = peer_average_multiples(peers)
    year = latest_year(data)
    ebitda = ebitda_by_year(data)[year]
    bs = data["balance_sheet_latest"]
    shares = data["market_data"]["diluted_shares_outstanding"]

    implied_ev = avg["avg_ev_ebitda"] * ebitda if avg["avg_ev_ebitda"] else None
    implied_price_ev_ebitda = None
    if implied_ev is not None:
        implied_equity_value = implied_ev - bs["total_debt"] + bs["cash_and_equivalents"]
        implied_price_ev_ebitda = implied_equity_value / shares

    implied_price_pe = (avg["avg_pe"] * data["market_data"]["ttm_eps"]) if avg["avg_pe"] else None

    return {
        "peer_avg_ev_ebitda": avg["avg_ev_ebitda"],
        "peer_avg_pe": avg["avg_pe"],
        "implied_ev_from_ebitda_multiple": implied_ev,
        "implied_share_price_ev_ebitda": implied_price_ev_ebitda,
        "implied_share_price_pe": implied_price_pe,
        "current_share_price": data["market_data"]["share_price"],
    }


def comps_table(data, peers):
    """Row-per-company table (peers + target) for the report/dashboard."""
    rows = [{
        "ticker": p["ticker"],
        "name": p["name"],
        "market_cap": p["market_cap"],
        "revenue": p.get("ttm_revenue"),
        "pe": p.get("pe_ratio"),
        "ev_ebitda": p.get("ev_ebitda"),
    } for p in peers]

    tm = target_multiples(data)
    rows.append({
        "ticker": data["ticker"],
        "name": f"{data['company']}  (subject company)",
        "market_cap": data["market_data"]["market_cap"],
        "revenue": data["income_statement"][latest_year(data)]["revenue"],
        "pe": tm["pe"],
        "ev_ebitda": round(tm["ev_ebitda"], 2),
    })
    return rows


if __name__ == "__main__":
    import sys
    from financials import load_financials
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NKE"
    data = load_financials(ticker)
    peers = load_peers(data)
    print("Peer averages:", peer_average_multiples(peers))
    print("Target's own multiples:", target_multiples(data))
    print("Implied valuation from comps:", implied_valuation_from_comps(data, peers))
    print("\nComps table:")
    for row in comps_table(data, peers):
        print(row)
