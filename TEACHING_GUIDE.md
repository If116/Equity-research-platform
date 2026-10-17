# Teaching Guide: How This Platform Works (and How to Explain It)

This doc exists for one reason: so you can sit across from an interviewer, have
them point at a number in the PDF, and explain *exactly* where it came from and
why it's a defensible way to compute it. Each section below pairs a finance
concept with the precise function that implements it.

Read this top to bottom once, then use it as a reference before interviews.

---

## 1. The data layer: why nothing is hardcoded to one company

**Concept:** Real analysts don't special-case their models per company — the
*method* is the same for Nike or Lululemon or anyone else; only the *inputs*
change.

**Where it lives:** `data/companies/<TICKER>.json`. Every function in
`financials.py`, `comps.py`, and `valuation.py` takes a `data` dict loaded from
one of these files and never references a specific company name or number.
`data/peer_universe.json` is the shared pool of peer profiles — any company's
`"peers"` list just names which tickers from that pool to pull in.

**How to explain it:** "I separated the data from the logic. `analysis.py
LULU` and `analysis.py NKE` run the identical pipeline — the only thing that
changes is which JSON file gets loaded. That's what makes it a platform
instead of a one-off script."

**The gotcha I actually hit:** My first version had Nike's 5-year FCF growth
path hardcoded as a module-level constant in `valuation.py`. It worked fine
for Nike. Then I ran it for Lululemon and got a DCF implying the stock was
worth nearly 2x its trading price — because the code was silently reusing
*Nike's* "post-trough recovery" growth story on a completely different
company with its own (much worse) outlook. I fixed this by moving growth
assumptions into each company's own `dcf_assumptions` block (see §5). This is
a great interview anecdote: it shows you understand that a DCF's output is
only as good as its growth/discount-rate *thesis*, not just the math.

---

## 2. Revenue, margins, and growth — `financials.py`

- **Revenue growth** (`revenue_growth`): simple year-over-year `%Δ`. Nothing
  fancy, but it's the first thing anyone asks about a company.
- **EBIT margin**: pulled directly from the data (`ebit / revenue`), since
  operating income is usually disclosed directly in a 10-K.
- **EBITDA** (`ebitda_by_year`): `EBIT + D&A`. This is the "back into it"
  version — some companies report EBITDA directly, but computing it from EBIT
  and the cash-flow statement's D&A line is the standard approach when they
  don't, and it's worth being able to do by hand.
- **FCF margin**: `Free Cash Flow / Revenue`, where FCF itself = Cash From
  Operations − Capex (computed upstream, stored directly in the data file).

**Interview-ready line:** "EBITDA strips out financing structure (interest),
tax jurisdiction, and capital intensity (D&A) so you can compare an
asset-light company like Lululemon to a more capital-intensive one like Nike
on operating performance alone."

---

## 3. ROIC and leverage — the "is this a good business" metrics

### ROIC (`roic()` in `financials.py`)

```
ROIC = NOPAT / Invested Capital
NOPAT = EBIT × (1 − tax rate)
Invested Capital = Total Debt + Equity − Cash
```

Equity isn't pulled from one disclosed line — it's **backed into** from
`Total Assets − Total Liabilities`, where total liabilities is the sum of
current liabilities, long-term debt, operating lease liabilities, and
deferred taxes/other. This is exactly what you'd do with a real 10-K balance
sheet when the "total stockholders' equity" line isn't broken out the way you
need.

**Why it matters:** ROIC answers "for every dollar invested in the business,
how many cents of after-tax operating profit come out?" Compare it to WACC
(§5) — if ROIC > WACC, the company is creating value with each new dollar it
invests; if ROIC < WACC, it's actually destroying value even if it's
"profitable" on paper.

**The platform's own finding, as a talking point:** Lululemon's ROIC comes
out to ~55% versus Nike's ~18%. That's not a bug — Lululemon runs an
asset-light, debt-free model with high margins, so every dollar of invested
capital works much harder. This is a real, explainable, structural difference
between the two businesses, and it's the kind of thing you want to be able to
say out loud in an interview rather than just reading off a number.

### Leverage (`leverage_ratios()`)

`Net Debt / EBITDA` and `Total Debt / EBITDA` — the standard credit-risk
lens. Nike carries real funded debt (~$10.5B) with modest leverage (~2.3x
total debt/EBITDA, ~0.3x net of its large cash balance). Lululemon carries
**zero** funded debt, so its leverage ratios are negative (net cash position)
— another structural contrast worth being able to narrate.

---

## 4. Comparable company analysis — `comps.py`

**The idea:** find public companies similar enough to the target that their
trading multiples (P/E, EV/EBITDA) tell you something about what the market
is willing to pay for a dollar of the target's earnings or EBITDA.

**The code:**
- `load_peers()` resolves a target's `"peers"` ticker list against the shared
  `peer_universe.json` pool.
- `peer_average_multiples()` averages EV/EBITDA and P/E across whichever
  peers have that data (skipping `None`s — real data is messy; Deckers, for
  instance, doesn't have a clean P/E in this dataset, so it's excluded from
  that average rather than treated as zero).
- `implied_valuation_from_comps()` applies the peer average multiple to the
  *target's own* EBITDA/EPS to back into an implied enterprise value, then an
  implied equity value, then an implied share price.

**Why the two multiples can disagree (and they do, a lot, in this
platform's own output):** EV/EBITDA is capital-structure-neutral — it doesn't
care how much debt a company carries. P/E very much does, because interest
expense sits above net income. When a company's own multiple (what the market
actually pays) differs a lot from the peer average, that's not noise — it's
the market pricing in something the simple comp math can't see (brand
strength, growth expectations, balance-sheet risk). Nike trades at a *premium*
EV/EBITDA to its peers despite a depressed earnings year — that premium is
either justified by the brand and turnaround story, or it's priced for a
recovery that hasn't happened yet. That tension **is** the analysis.

---

## 5. The DCF — `valuation.py`

This is the part most likely to get interrogated line-by-line, so know it cold.

### Step 1: WACC (`wacc()`)

```
WACC = (E/V) × Cost of Equity + (D/V) × After-tax Cost of Debt
Cost of Equity (CAPM) = Risk-free rate + Beta × Equity Risk Premium
After-tax Cost of Debt = Pre-tax Cost of Debt × (1 − tax rate)
```

- `E` = market cap, `D` = total (funded) debt, `V = E + D`.
- For an all-equity company like Lululemon (`D = 0`), WACC collapses to just
  the cost of equity — the code handles this explicitly rather than dividing
  by zero.

**Interview-ready line:** "WACC is the blended return investors demand for
funding this specific company, weighted by how much of its capital structure
is equity versus debt. Debt is 'cheaper' than equity on a nominal basis, but
you have to tax-affect it because interest is tax-deductible."

### Step 2: Project FCF (`project_fcf()`)

Takes a base-year FCF and a 5-year growth path (a *list* of growth rates per
year, not one flat rate) and compounds forward. Using a path instead of one
number is what lets you encode a thesis like "decline this year, flat next
year, then recover" (Lululemon) versus "steady recovery" (Nike) instead of
smearing it into one average rate.

### Step 3: Terminal value (Gordon Growth)

```
Terminal Value = Final Year FCF × (1 + terminal growth) / (WACC − terminal growth)
```

This captures everything that happens *after* the explicit 5-year window,
assuming the business grows at a stable, sustainable rate forever (usually
pegged near long-run GDP growth, ~2-2.5%). **If WACC ≤ terminal growth, the
formula breaks** (you'd be dividing by zero or a negative number) — the
sensitivity grid explicitly checks for this and returns `None` rather than a
nonsense number.

### Step 4: Enterprise Value → Equity Value → Share Price

```
Enterprise Value = Σ PV(explicit FCFs) + PV(Terminal Value)
Equity Value = Enterprise Value − Total Debt + Cash
Implied Share Price = Equity Value / Diluted Shares Outstanding
```

### Step 5: Sensitivity grid (`sensitivity_grid()`)

A DCF's output is extremely sensitive to two inputs you can't know for
certain: WACC and terminal growth. The grid recomputes the implied price
across a range of both, which is exactly what you'd build in Excel as a
"data table" — this is the single most common thing interviewers ask you to
produce by hand, so be able to explain *why* it exists (to show how fragile
or robust your "base case" number actually is) not just that it does.

**Where company-specific assumptions plug in:** all of the above pulls its
inputs from `assumptions(data)`, which reads a `dcf_assumptions` block out of
the company's own JSON file (growth path, terminal growth, risk-free rate,
ERP, cost of debt, tax rate) — see each company's `"note"` field for the
plain-English thesis behind those numbers. This is the fix described in §1.

---

## 6. How to extend this to a company your interviewer picks on the spot

There are two ways to onboard a new company. Know both — which one you'd
reach for, and why, is itself a good answer to "how would you extend this."

### The fast way: `add_company.py`

```bash
python3 add_company.py TICKER --peers PEER1,PEER2,PEER3
```

This calls `fetch_company_data.py`, which pulls real financials for that
ticker via `yfinance` (3 years of income statement, cash flow, latest
balance sheet, current market data) and writes `data/companies/TICKER.json`
automatically, then runs the model, the PDF, and the dashboard in one shot.
It's fast, and it's genuinely useful for getting a first look at a company.

**It is not a substitute for understanding the company.** The fetch step
writes a flat, clearly-labeled *placeholder* growth path into
`dcf_assumptions` — never a real thesis — because auto-generating one would
reintroduce the exact bug described in §1 (borrowing a growth story that
doesn't belong to this company) one layer deeper. `add_company.py` prints a
reminder of this every time. The honest move in an interview: run the fast
path to get the data loaded, then say out loud that you're about to go
write your own growth thesis before trusting any DCF number it produced.

### The slow way: by hand, from `_TEMPLATE.json`

Worth doing at least once so the fast path isn't a black box to you:

1. **Copy `data/companies/_TEMPLATE.json`** — every field has a sourcing hint.
2. **Pull 3 years of income statement data** (revenue, EBIT, net income,
   diluted EPS) from the company's 10-K or a source like stockanalysis.com.
3. **Pull the cash flow statement** (D&A, capex) for the same years, and
   compute FCF = CFO − capex.
4. **Pull one year of balance sheet detail** (cash, short-term investments,
   total assets, current liabilities, long-term debt, operating lease
   liabilities, deferred taxes/other) — enough to back into equity for ROIC.
5. **Pull current market data** (share price, market cap, diluted shares,
   trailing P/E, beta).
6. **Decide on 3-5 real peers** and add any that aren't already in
   `peer_universe.json`.
7. **Write your own `dcf_assumptions`** — don't reuse another company's
   growth path. Ask: is this company recovering, declining, stable, or
   compounding? That answer determines the shape of your 5-year growth path.
8. **Run it:** `python3 add_company.py TICKER --skip-fetch` (runs the model,
   PDF, and dashboard against your hand-built file without touching the
   network).

If you can talk through both paths unprompted — and explain *why* the fast
path still needs you to write step 7 yourself — you've demonstrated you
understand the platform rather than memorized one company's numbers.

---

## 7. Likely interview questions and where the answer lives

| Question | Where to look |
|---|---|
| "Walk me through your DCF." | §5 above, `valuation.py` top to bottom |
| "Why EV/EBITDA *and* P/E for comps, not just one?" | §4, the capital-structure-neutrality point |
| "What's your terminal growth assumption and why?" | Each company's `dcf_assumptions.terminal_growth` (~2.5%, pegged to long-run nominal GDP) |
| "What would break this model?" | WACC ≤ terminal growth (§5 Step 3); a peer set with no comparable business model; FCF data that's estimated rather than disclosed (flagged explicitly in `LULU.json`'s `notes` field) |
| "How would you value a company with negative FCF?" | The DCF as written would produce a negative/nonsensical price — you'd need a longer explicit projection window until FCF turns positive, or switch to a revenue-multiple approach entirely. Good to say even though the code doesn't handle it. |
| "Why does Nike's DCF land near its market price but Lululemon's doesn't?" | Honest answer: partly a real "market still pricing in execution risk" story, and partly because LULU's FCF inputs here are partially *estimated* (flagged in the data file) rather than pulled verbatim from a cash flow statement — a great example of knowing the limits of your own model. |
| "How does your platform handle a company you've never looked at before?" | `add_company.py` + `fetch_company_data.py` (§6) — pulls real data via yfinance automatically, but deliberately refuses to auto-generate a growth thesis, because that's the one part that has to come from you. |
