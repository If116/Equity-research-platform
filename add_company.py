"""
add_company.py

The one-command entry point for analyzing a NEW company:

    python3 add_company.py TSLA --peers F,GM,RIVN

This chains together the whole platform:
  1. fetch_company_data.py  -> pulls real financials via yfinance, writes data/companies/TSLA.json
  2. analysis.py             -> computes ROIC/leverage/comps/DCF, writes charts/ + data/output_TSLA.json
  3. generate_report.py       -> builds research_report_TSLA.pdf
  4. dashboard_builder.py      -> builds dashboards/TSLA_dashboard.html

If data/companies/TICKER.json already exists, this SKIPS the fetch step by
default (so you don't clobber a file you've hand-edited with your own
dcf_assumptions) and just re-runs steps 2-4 on the existing file. Pass
--refetch to force a fresh pull.

IMPORTANT: step 1 needs real internet access and the yfinance package. Steps
2-4 are pure local computation and don't need network at all -- so if the
fetch fails (bad ticker, no internet, Yahoo rate-limiting, a field yfinance
doesn't expose for this company), you can still hand-edit the JSON it
partially wrote (or copy data/companies/_TEMPLATE.json) and run steps 2-4
yourself.
"""

import argparse
import sys
from pathlib import Path

BASE = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser(description="Analyze a new company end-to-end: fetch -> model -> report -> dashboard.")
    parser.add_argument("ticker", help="e.g. TSLA, AAPL, DECK")
    parser.add_argument("--peers", default="", help="comma-separated peer tickers, e.g. F,GM,RIVN")
    parser.add_argument("--refetch", action="store_true", help="re-fetch data even if data/companies/<TICKER>.json already exists")
    parser.add_argument("--skip-fetch", action="store_true", help="skip the fetch step entirely and just run analysis/report/dashboard on the existing file")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    company_path = BASE / "data" / "companies" / f"{ticker}.json"

    # --- Step 1: fetch ---
    if args.skip_fetch:
        if not company_path.exists():
            print(f"ERROR: --skip-fetch was passed but {company_path} doesn't exist. "
                  f"Either remove --skip-fetch or create that file first (see data/companies/_TEMPLATE.json).")
            sys.exit(1)
        print(f"Skipping fetch, using existing {company_path}")
    else:
        if company_path.exists() and not args.refetch:
            print(f"{company_path} already exists -- skipping fetch (pass --refetch to overwrite).")
        else:
            import fetch_company_data as fcd
            print(f"Fetching {ticker} via yfinance...")
            try:
                data, warnings = fcd.fetch_company(ticker)
            except Exception as e:
                print(f"\nFETCH FAILED: {e}")
                print("You can still hand-build data/companies/{}.json from _TEMPLATE.json and re-run with --skip-fetch.".format(ticker))
                sys.exit(1)

            if args.peers:
                peer_tickers = [p.strip().upper() for p in args.peers.split(",") if p.strip()]
                data["peers"] = peer_tickers
                _merge_peers_into_universe(peer_tickers, fcd, warnings)

            if warnings:
                print(f"\n{len(warnings)} WARNING(S) -- review data/companies/{ticker}.json before trusting it:")
                for w in warnings:
                    print(f"  - {w}")

            path = fcd.save_company(ticker, data, force=args.refetch)
            print(f"Wrote {path}")
            print(f"\n*** Review {path.name}'s dcf_assumptions before trusting the DCF output. ***")
            print("    It currently has a flat, placeholder growth path -- see TEACHING_GUIDE.md section 1 for why that matters.\n")

    # --- Step 2: analysis ---
    print(f"Running analysis for {ticker}...")
    import analysis
    try:
        analysis.run(ticker)
    except KeyError as e:
        print(f"ERROR during analysis: missing field {e}. Check {company_path} against data/companies/_TEMPLATE.json.")
        sys.exit(1)

    # --- Step 3: report ---
    print(f"Building PDF report for {ticker}...")
    import generate_report
    generate_report.build_report(ticker)

    # --- Step 4: dashboard ---
    print(f"Building dashboard for {ticker}...")
    import dashboard_builder
    dash_path = dashboard_builder.build_dashboard(ticker)

    print(f"\nDone. Outputs for {ticker}:")
    print(f"  - data/companies/{ticker}.json   (the data you may still want to review/edit)")
    print(f"  - data/output_{ticker}.json       (computed metrics)")
    print(f"  - charts/{ticker}/                 (PNG charts)")
    print(f"  - research_report_{ticker}.pdf      (PDF report)")
    print(f"  - {dash_path}  (open this in a browser)")


def _merge_peers_into_universe(peer_tickers, fcd_module, warnings):
    import json
    universe_path = BASE / "data" / "peer_universe.json"
    with open(universe_path) as f:
        universe = json.load(f)
    existing = {c["ticker"] for c in universe["companies"]}

    for pt in peer_tickers:
        if pt in existing:
            continue
        try:
            profile = fcd_module.fetch_peer_profile(pt)
            universe["companies"].append(profile)
            print(f"  Added peer {pt} to peer_universe.json")
        except Exception as e:
            warnings.append(f"Could not fetch peer profile for '{pt}': {e}. Add it to peer_universe.json manually.")

    with open(universe_path, "w") as f:
        json.dump(universe, f, indent=2)


if __name__ == "__main__":
    main()
