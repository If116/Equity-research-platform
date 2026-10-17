# Equity Research & Valuation Platform

A Python pipeline that takes ANY public company's ticker and produces a full
equity research workup: operating/credit metrics (ROIC, leverage, margins),
a comparable-company (comps) analysis, a DCF valuation with a WACC build-up
and sensitivity grid, a formatted PDF research report, and an interactive
web dashboard.

```bash
python3 add_company.py TSLA --peers F,GM,RIVN
```

That one command fetches real financials for the ticker via `yfinance`,
runs the full model, and produces a PDF report and a live dashboard. It
ships with two companies already built out end-to-end this way —
**NIKE (NKE)** and **Lululemon (LULU)** — on the exact same codebase, which
is the point: this is a platform, not a one-off script for one company. See
`TEACHING_GUIDE.md` for a full concept-by-concept walkthrough (what each
metric means, how the code computes it, and how to explain it in an
interview).

   **Interactive dashboards:** [NKE](https://if116.github.io/Equity-research-platform/dashboards/NKE_dashboard.html) · [LULU](https://if116.github.io/Equity-research-platform/dashboards/LULU_dashboard.html)
## Project structure

```
equity-research-platform/
├── add_company.py              # ONE-COMMAND entry point: fetch -> model -> report -> dashboard
├── fetch_company_data.py        # pulls real financials for any ticker via yfinance
├── dashboard_builder.py           # generates the interactive dashboard for any analyzed company
├── financials.py                    # growth/margins/ROIC/leverage -- company-agnostic
├── comps.py                           # peer multiples, implied comps valuation
├── valuation.py                         # WACC (CAPM), DCF, sensitivity grid
├── analysis.py                            # orchestrates financials/comps/valuation, writes output JSON
├── generate_report.py                       # builds the PDF report with data-driven narrative text
├── requirements.txt
├── TEACHING_GUIDE.md                           # concept-by-concept explainer + interview prep
├── data/
│   ├── companies/
│   │   ├── NKE.json                               # Nike's financials (sourced from FY23-25 10-Ks)
│   │   ├── LULU.json                               # Lululemon's financials (sourced from its FY25 10-K)
│   │   └── _TEMPLATE.json                           # copy this to onboard a new company by hand
│   ├── peer_universe.json                             # shared pool of peer company profiles
│   └── output_<TICKER>.json                             # consolidated pipeline output (generated)
├── charts/<TICKER>/                                       # PNG charts per company (generated)
├── dashboards/<TICKER>_dashboard.html                       # interactive dashboard per company (generated)
└── research_report_<TICKER>.pdf                               # final report per company (generated)
```

## How to run it

**The fast path -- analyze a brand new company with one command:**

```bash
pip install -r requirements.txt
python3 add_company.py TSLA --peers F,GM,RIVN
```

This fetches Tesla's real financials via `yfinance`, computes every metric,
and writes a PDF report and an interactive dashboard. It needs internet
access (the fetch step calls Yahoo Finance) -- everything downstream of that
is local computation.

**Important:** the auto-fetched `dcf_assumptions` is a flat, clearly-labeled
placeholder, not a real thesis -- `add_company.py` prints a reminder to go
edit `data/companies/TSLA.json` yourself before trusting the DCF output
(see `TEACHING_GUIDE.md` §1 for why reusing a generic or borrowed growth
path produces a wrong-but-confident-looking number). Once you've edited it,
re-run `python3 analysis.py TSLA && python3 generate_report.py TSLA &&
python3 dashboard_builder.py TSLA` to regenerate with your own assumptions
(the fetch step won't repeat and clobber your edits unless you pass
`--refetch`).

**Rerunning or tweaking an existing company:**

```bash
python3 analysis.py NKE && python3 generate_report.py NKE
python3 dashboard_builder.py NKE

# Each module also runs standalone and prints its own output:
python3 financials.py LULU
python3 comps.py NKE
python3 valuation.py NKE
```

**Onboarding a company by hand instead** (more control, more effort -- good
for really internalizing where every number comes from): copy
`data/companies/_TEMPLATE.json`, fill it in from a real 10-K using the
inline sourcing hints, then run
`python3 add_company.py TICKER --skip-fetch`. Full walkthrough in
`TEACHING_GUIDE.md` §6.

## What makes this a "platform" and not a script

The first version of this project had Nike's numbers hardcoded directly into
the valuation logic and the PDF narrative text. Two things forced a rewrite:

1. **DCF assumptions are company-specific, not reusable.** Running the
   original code on Lululemon silently reused *Nike's* FCF growth path and
   produced a DCF implying ~2x upside — not because the math was wrong, but
   because the growth thesis was wrong for that company. Growth path,
   terminal growth, and WACC inputs now live in each company's own
   `dcf_assumptions` block instead of as constants in `valuation.py`.
2. **Report narrative text has to be generated from data, not written once.**
   The PDF's prose (financial trend, comps commentary, DCF discussion,
   summary) is now built by functions in `generate_report.py` that read the
   actual numbers for whatever company you pass in, rather than describing
   Nike's FY2025 turnaround regardless of which company's report you're
   generating.

Both of these are good interview talking points in their own right —
they show you understand *why* a model built for one company doesn't
automatically generalize, which is a more sophisticated point than "I built
a DCF."

## Data & methodology notes

- Nike's historicals (FY2023-FY2025) and Lululemon's historicals
  (FY2023-FY2025) are sourced from their respective Form 10-K filings and
  earnings releases, cross-checked where possible (e.g. Lululemon's balance
  sheet reconciles exactly: Total Assets − Total Equity = Total Liabilities).
- Where a figure isn't directly disclosed in the sources pulled (e.g.
  Lululemon's exact FY2025 capex), it's modeled with a clearly documented
  approximation in that company's `notes` field -- flagged, not hidden.
- Peer comps figures are approximate, compiled from public market-data
  aggregators as of ~September 2026.
- This is an educational/portfolio project, not investment research.

## Putting this on GitHub

```bash
cd equity-research-platform
git init
git add .
git commit -m "Equity research & valuation platform (NKE, LULU)"
git branch -M main
git remote add origin https://github.com/<your-username>/equity-research-platform.git
git push -u origin main
```

A couple of things worth doing before you link it on your resume:
- Add a 1-2 line project description + the live dashboard link to the repo's
  "About" section on GitHub.
- Consider adding 2-3 screenshots (a PDF page, the dashboard) to the top of
  this README — recruiters skim repos, they don't usually run them.
- Double-check `.gitignore` excludes `__pycache__/` (a minimal one is below).

```
# .gitignore
__pycache__/
*.pyc
.DS_Store
```

## Suggested resume bullet

> **Equity Research & Valuation Platform | Python, Financial Modeling (DCF, Comps)**
> Built a Python platform that pulls real financial data for any public
> company (via the Yahoo Finance API) and generates a full equity research
> workup — DCF valuation with CAPM-derived WACC, comparable-company analysis,
> ROIC/leverage metrics, an automated PDF report, and an interactive
> dashboard; demonstrated end-to-end on NIKE and Lululemon.

The "for any public company" phrasing is now actually true, which is what
makes it defensible if an interviewer asks you to run it on a company you've
never touched before -- see `TEACHING_GUIDE.md` §6 for exactly how.

## A note on `fetch_company_data.py`

It was written and logic-tested (with mocked data standing in for yfinance's
actual network response -- see the transformation logic for every field
mapping) in an environment with no internet access, so it's never made a
real live call. Run it yourself the first time on a company you know well
and sanity-check the output against stockanalysis.com or the 10-K before
trusting it blindly -- it prints an explicit warning for every field it
couldn't find rather than silently guessing, so start by reading those.
yfinance's row labels also drift across tickers and package versions; if a
field comes back wrong or missing for your company, `_get_row()` in that
file is where you'd add another candidate label to try.

## Extending it further

- Add a third/fourth company and turn `comps.py` into a true sector screener.
- Add a Monte Carlo layer to the DCF (sample growth/WACC from distributions)
  instead of point estimates, to generate a distribution of implied prices.
- `fetch_company_data.py` currently only pulls 3 years of annual data --
  extend it to pull quarterly data too for a more current picture between
  10-K filings.
- Swap `yfinance` for the SEC EDGAR JSON API (`data.sec.gov`) for the
  income statement/balance sheet pull -- more authoritative (it's the actual
  filed XBRL data) but more work, since line-item tags vary by company.
