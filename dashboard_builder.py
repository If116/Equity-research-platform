"""
dashboard_builder.py

Generates the interactive equity-research dashboard (KPI cards, revenue/FCF
charts, comps table, live DCF sliders, sensitivity heatmap) for ANY company
that has already been run through analysis.py -- i.e. has a
data/output_<TICKER>.json file.

This is the same dashboard built by hand for NKE; it's now a template filled
in from that company's own data instead of a one-off file with NKE's numbers
typed directly into the JavaScript.

Usage:
    python3 dashboard_builder.py NKE
    python3 dashboard_builder.py LULU
    -> writes dashboards/<TICKER>_dashboard.html

Open the file directly in a browser, or publish it however you're hosting
dashboards (e.g. drag it into an artifact/preview tool).
"""

import json
import sys
from pathlib import Path

BASE = Path(__file__).parent
DASHBOARD_DIR = BASE / "dashboards"

# The static shell is unchanged from the original hand-built dashboard --
# only the DATA object and a few header strings are templated.
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__TICKER__ — Equity Research Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0b0e13; --panel: #12161e; --panel-2: #161b25; --border: #262d3a;
    --text: #e7eaf0; --text-dim: #8b93a5; --accent: #f97316; --accent-dim: #c2570f;
    --blue: #38bdf8; --green: #34d399; --red: #f87171;
    --mono: 'IBM Plex Mono', monospace; --sans: 'Space Grotesk', sans-serif; --radius: 3px;
  }
  :root:not([data-theme="light"]) { color-scheme: dark; }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme="dark"]) {
      --bg: #f5f6f8; --panel: #ffffff; --panel-2: #f0f1f4; --border: #d9dce2;
      --text: #12161e; --text-dim: #565f70;
    }
  }
  :root[data-theme="light"] {
    --bg: #f5f6f8; --panel: #ffffff; --panel-2: #f0f1f4; --border: #d9dce2;
    --text: #12161e; --text-dim: #565f70;
  }
  * { box-sizing: border-box; }
  html { scroll-padding-top: env(safe-area-inset-top, 0px); }
  html, body {
    height: 100%; margin: 0; background: var(--bg); color: var(--text);
    font-family: var(--sans); padding-top: env(safe-area-inset-top, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }
  body { -webkit-font-smoothing: antialiased; }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 28px 20px 60px; }
  header.top {
    display: flex; justify-content: space-between; align-items: flex-end;
    flex-wrap: wrap; gap: 14px; border-bottom: 1px solid var(--border);
    padding-bottom: 18px; margin-bottom: 26px;
  }
  .id-block { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  .ticker { font-size: 13px; letter-spacing: 0.08em; color: var(--accent); font-family: var(--mono); }
  h1 { font-size: 26px; margin: 2px 0 0; font-weight: 600; }
  .price-block { text-align: right; }
  .price { font-family: var(--mono); font-size: 30px; font-weight: 500; }
  .asof { color: var(--text-dim); font-size: 12px; margin-top: 2px; }
  .kpi-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1px; background: var(--border); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden; margin-bottom: 30px;
  }
  .kpi { background: var(--panel); padding: 16px 16px; }
  .kpi .label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.04em; }
  .kpi .value { font-family: var(--mono); font-size: 20px; margin-top: 6px; }
  .kpi .value.up { color: var(--green); }
  .kpi .value.down { color: var(--red); }
  section { margin-bottom: 34px; }
  .section-title {
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--text-dim); margin-bottom: 12px; font-family: var(--mono);
  }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px; }
  .chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 720px) { .chart-row { grid-template-columns: 1fr; } }
  .chart-box { height: 260px; }
  table { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 13px; }
  th, td { text-align: right; padding: 9px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--text-dim); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em; }
  tr.highlight td { color: var(--accent); font-weight: 600; }
  .scroll-x { overflow-x: auto; }
  .dcf-controls { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 18px; }
  @media (max-width: 720px) { .dcf-controls { grid-template-columns: 1fr; } }
  .slider-block label { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 8px; }
  .slider-block .val { font-family: var(--mono); color: var(--accent); }
  input[type=range] { width: 100%; accent-color: var(--accent); background: transparent; }
  .dcf-result-row { display: flex; gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
  .dcf-result-row > div { flex: 1; background: var(--panel); padding: 14px 16px; }
  .dcf-result-row .big { font-family: var(--mono); font-size: 22px; margin-top: 4px; }
  .heat-cell { border-radius: 2px; padding: 2px 4px; }
  footer { color: var(--text-dim); font-size: 11px; line-height: 1.6; border-top: 1px solid var(--border); padding-top: 16px; margin-top: 10px; }
  .theme-toggle {
    position: fixed; top: calc(16px + env(safe-area-inset-top, 0px)); right: 16px;
    background: var(--panel); border: 1px solid var(--border); color: var(--text-dim);
    font-family: var(--mono); font-size: 11px; padding: 6px 10px; border-radius: var(--radius); cursor: pointer;
  }
</style>
</head>
<body>
<button class="theme-toggle" id="themeToggle">theme</button>
<div class="wrap">
  <header class="top">
    <div class="id-block">
      <div>
        <div class="ticker">__TICKER__</div>
        <h1>__COMPANY_NAME__ — Equity Research Dashboard</h1>
      </div>
    </div>
    <div class="price-block">
      <div class="price" id="currentPriceLabel">$__CURRENT_PRICE__</div>
      <div class="asof">as of __AS_OF_DATE__ · built on __LATEST_FY__ data</div>
    </div>
  </header>

  <div class="kpi-grid" id="kpiGrid"></div>

  <section>
    <div class="section-title">Financial Trend — __YEAR_RANGE__</div>
    <div class="panel chart-row">
      <div class="chart-box"><canvas id="revenueChart"></canvas></div>
      <div class="chart-box"><canvas id="fcfChart"></canvas></div>
    </div>
  </section>

  <section>
    <div class="section-title">Comparable Company Analysis</div>
    <div class="panel scroll-x"><table id="compsTable"></table></div>
  </section>

  <section>
    <div class="section-title">DCF Valuation — Interactive</div>
    <div class="panel">
      <div class="dcf-controls">
        <div class="slider-block">
          <label>WACC <span class="val" id="waccVal">__WACC_PCT__%</span></label>
          <input type="range" id="waccSlider" min="__WACC_MIN__" max="__WACC_MAX__" step="0.1" value="__WACC_PCT__">
        </div>
        <div class="slider-block">
          <label>Terminal growth <span class="val" id="growthVal">__TERMINAL_GROWTH_PCT__%</span></label>
          <input type="range" id="growthSlider" min="1" max="4" step="0.1" value="__TERMINAL_GROWTH_PCT__">
        </div>
      </div>
      <div class="dcf-result-row">
        <div><div class="section-title" style="margin-bottom:4px;">Implied share price</div><div class="big" id="dcfImplied">—</div></div>
        <div><div class="section-title" style="margin-bottom:4px;">vs. current price</div><div class="big" id="dcfDelta">—</div></div>
        <div><div class="section-title" style="margin-bottom:4px;">Implied enterprise value</div><div class="big" id="dcfEV">—</div></div>
      </div>
    </div>
  </section>

  <section>
    <div class="section-title">Sensitivity — Implied Price (WACC × Terminal Growth)</div>
    <div class="panel scroll-x"><table id="sensTable"></table></div>
  </section>

  <footer>
    Built as an independent educational/portfolio project. __SOURCES_NOTE__ Not investment research —
    all assumptions (WACC build-up, FCF growth path, terminal growth) are adjustable above and documented in the
    accompanying Python source (valuation.py, comps.py, financials.py). This dashboard is generated by
    dashboard_builder.py from data/output___TICKER__.json -- it is not hand-written per company.
  </footer>
</div>

<script>
const DATA = __DATA_JSON__;

const kpis = [
  {label:"Current price", value:`$${DATA.currentPrice.toFixed(2)}`},
  {label:"DCF implied price", value:`$${DATA.dcfImplied.toFixed(2)}`, cls: DATA.dcfImplied >= DATA.currentPrice ? "up" : "down"},
  {label:"Comps EV/EBITDA implied", value: DATA.impliedCompsEvEbitda ? `$${DATA.impliedCompsEvEbitda.toFixed(2)}` : "n/a", cls: DATA.impliedCompsEvEbitda && DATA.impliedCompsEvEbitda < DATA.currentPrice ? "down" : "up"},
  {label:"Comps P/E implied", value: DATA.impliedCompsPe ? `$${DATA.impliedCompsPe.toFixed(2)}` : "n/a"},
  {label:`ROIC (${DATA.latestFy})`, value:`${DATA.roic.toFixed(1)}%`},
  {label:"Net Debt / EBITDA", value:`${DATA.netDebtToEbitda.toFixed(2)}x`},
];
document.getElementById("kpiGrid").innerHTML = kpis.map(k =>
  `<div class="kpi"><div class="label">${k.label}</div><div class="value ${k.cls||''}">${k.value}</div></div>`
).join("");

function chartTextColor() { return getComputedStyle(document.documentElement).getPropertyValue('--text-dim').trim(); }
Chart.defaults.font.family = "'IBM Plex Mono', monospace";
Chart.defaults.font.size = 11;

const revChart = new Chart(document.getElementById('revenueChart'), {
  data: { labels: DATA.years, datasets: [
    {type:'bar', label:'Revenue ($M)', data: DATA.revenue, backgroundColor:'#38bdf8', yAxisID:'y', borderRadius:2},
    {type:'line', label:'EBIT margin (%)', data: DATA.ebitMargin, borderColor:'#f97316', backgroundColor:'#f97316', yAxisID:'y1', tension:0.3, pointRadius:3},
  ]},
  options: { responsive:true, maintainAspectRatio:false,
    plugins:{ legend:{labels:{color: chartTextColor()}}, title:{display:true, text:'Revenue & EBIT Margin', color: chartTextColor()} },
    scales: { y:{position:'left', ticks:{color:chartTextColor()}, grid:{color:'rgba(128,128,128,0.15)'}},
              y1:{position:'right', ticks:{color:chartTextColor()}, grid:{drawOnChartArea:false}},
              x:{ticks:{color:chartTextColor()}, grid:{display:false}} } }
});
const fcfChart = new Chart(document.getElementById('fcfChart'), {
  type:'bar',
  data: { labels: DATA.years, datasets:[{label:'FCF ($M)', data: DATA.fcf, backgroundColor:'#34d399', borderRadius:2}] },
  options: { responsive:true, maintainAspectRatio:false,
    plugins:{ legend:{display:false}, title:{display:true, text:'Free Cash Flow', color: chartTextColor()} },
    scales: { y:{ticks:{color:chartTextColor()}, grid:{color:'rgba(128,128,128,0.15)'}}, x:{ticks:{color:chartTextColor()}, grid:{display:false}} } }
});

function fmtMoney(v){ return v==null ? "n/a" : `$${v.toLocaleString()}`; }
function fmtX(v){ return v==null ? "n/a" : `${v.toFixed(1)}x`; }
const compsHead = `<tr><th>Ticker</th><th>Mkt Cap ($M)</th><th>Revenue ($M)</th><th>P/E</th><th>EV/EBITDA</th></tr>`;
const compsRows = DATA.comps.map(c => `<tr ${c.highlight?'class="highlight"':''}><td>${c.t}</td><td>${fmtMoney(c.mc)}</td><td>${fmtMoney(c.rev)}</td><td>${fmtX(c.pe)}</td><td>${fmtX(c.ev)}</td></tr>`).join("");
document.getElementById("compsTable").innerHTML = compsHead + compsRows;

function dcfPrice(waccPct, gPct) {
  const wacc = waccPct/100, g = gPct/100;
  if (wacc <= g) return null;
  let fcf = DATA.baseFCF;
  const fcfs = DATA.growthPath.map(gr => { fcf = fcf*(1+gr); return fcf; });
  const pv = fcfs.map((f,i) => f/Math.pow(1+wacc, i+1));
  const tv = fcfs[fcfs.length-1]*(1+g)/(wacc-g);
  const pvTv = tv/Math.pow(1+wacc, fcfs.length);
  const ev = pv.reduce((a,b)=>a+b,0) + pvTv;
  const equity = ev - DATA.totalDebt + DATA.cash;
  return { price: equity/DATA.shares, ev };
}

function updateDcf() {
  const wacc = parseFloat(document.getElementById('waccSlider').value);
  const g = parseFloat(document.getElementById('growthSlider').value);
  document.getElementById('waccVal').textContent = wacc.toFixed(2)+'%';
  document.getElementById('growthVal').textContent = g.toFixed(1)+'%';
  const result = dcfPrice(wacc, g);
  if (!result) {
    document.getElementById('dcfImplied').textContent = 'n/a (WACC ≤ g)';
    document.getElementById('dcfDelta').textContent = '—';
    document.getElementById('dcfEV').textContent = '—';
    return;
  }
  document.getElementById('dcfImplied').textContent = `$${result.price.toFixed(2)}`;
  const delta = (result.price/DATA.currentPrice - 1)*100;
  const deltaEl = document.getElementById('dcfDelta');
  deltaEl.textContent = `${delta>=0?'+':''}${delta.toFixed(1)}%`;
  deltaEl.style.color = delta>=0 ? 'var(--green)' : 'var(--red)';
  document.getElementById('dcfEV').textContent = `$${Math.round(result.ev).toLocaleString()}M`;
  renderSensitivity(wacc);
}
document.getElementById('waccSlider').addEventListener('input', updateDcf);
document.getElementById('growthSlider').addEventListener('input', updateDcf);

function renderSensitivity(centerWacc) {
  const waccRows = [-1, -0.5, 0, 0.5, 1].map(d => +(centerWacc + d).toFixed(2));
  const gCols = [1.5, 2.0, 2.5, 3.0, 3.5];
  let html = '<tr><th>WACC \\ g</th>' + gCols.map(g=>`<th>${g.toFixed(1)}%</th>`).join('') + '</tr>';
  waccRows.forEach(w => {
    html += `<tr><th>${w.toFixed(2)}%</th>`;
    gCols.forEach(g => {
      const r = dcfPrice(w, g);
      if (!r) { html += `<td>n/a</td>`; return; }
      const diff = r.price/DATA.currentPrice - 1;
      const intensity = Math.min(Math.abs(diff)*3, 0.55);
      const color = diff >= 0 ? `rgba(52,211,153,${intensity})` : `rgba(248,113,113,${intensity})`;
      html += `<td><span class="heat-cell" style="background:${color}">$${r.price.toFixed(2)}</span></td>`;
    });
    html += '</tr>';
  });
  document.getElementById('sensTable').innerHTML = html;
}

updateDcf();

const themeBtn = document.getElementById('themeToggle');
themeBtn.addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  [revChart, fcfChart].forEach(c => {
    c.options.plugins.legend.labels.color = chartTextColor();
    if (c.options.plugins.title) c.options.plugins.title.color = chartTextColor();
    Object.values(c.options.scales).forEach(s => { if (s.ticks) s.ticks.color = chartTextColor(); });
    c.update();
  });
});
</script>
</body>
</html>
"""


def build_dashboard(ticker):
    base = Path(__file__).parent
    with open(base / "data" / f"output_{ticker}.json") as f:
        out = json.load(f)
    with open(base / "data" / "companies" / f"{ticker}.json") as f:
        company = json.load(f)

    summary = out["financial_summary"]
    years = [r["fiscal_year"] for r in summary]
    revenue = [r["revenue"] for r in summary]
    ebit_margin = [round(r["ebit_margin"] * 100, 1) for r in summary]
    fcf = [r["fcf"] for r in summary]

    comps = []
    for row in out["comps_table"]:
        comps.append({
            "t": row["ticker"],
            "n": row["name"],
            "mc": row["market_cap"],
            "rev": row["revenue"],
            "pe": row["pe"],
            "ev": row["ev_ebitda"],
            "highlight": row["ticker"] == ticker,
        })

    bs = company["balance_sheet_latest"]
    mkt = company["market_data"]
    dcf_assump = company.get("dcf_assumptions", {})

    data_obj = {
        "currentPrice": out["current_price"],
        "shares": mkt["diluted_shares_outstanding"],
        "totalDebt": bs["total_debt"],
        "cash": bs["cash_and_equivalents"],
        "baseFCF": summary[-1]["fcf"],
        "growthPath": dcf_assump.get("growth_path", [0.03] * 5),
        "years": years,
        "revenue": revenue,
        "ebitMargin": ebit_margin,
        "fcf": fcf,
        "roic": round(out["roic"] * 100, 1),
        "netDebtToEbitda": round(out["leverage"]["net_debt_to_ebitda"], 2),
        "comps": comps,
        "impliedCompsEvEbitda": out["implied_valuation_comps"]["implied_share_price_ev_ebitda"],
        "impliedCompsPe": out["implied_valuation_comps"]["implied_share_price_pe"],
        "dcfImplied": out["dcf_result"]["implied_share_price"],
        "latestFy": out["financial_summary"][-1]["fiscal_year"],
    }

    wacc_pct = round(out["wacc_buildup"]["wacc"] * 100, 2)
    terminal_growth_pct = round(out["dcf_result"]["terminal_growth_used"] * 100, 1)

    sources_note = "Sources: " + "; ".join(company.get("sources", [])) + "."

    html = (_TEMPLATE
            .replace("__TICKER__", ticker)
            .replace("__COMPANY_NAME__", out["company"])
            .replace("__CURRENT_PRICE__", f"{out['current_price']:.2f}")
            .replace("__AS_OF_DATE__", out["as_of_date"])
            .replace("__LATEST_FY__", out["financial_summary"][-1]["fiscal_year"])
            .replace("__YEAR_RANGE__", f"{years[0]}–{years[-1]}")
            .replace("__WACC_PCT__", str(wacc_pct))
            .replace("__WACC_MIN__", str(max(round(wacc_pct - 3), 1)))
            .replace("__WACC_MAX__", str(round(wacc_pct + 4)))
            .replace("__TERMINAL_GROWTH_PCT__", str(terminal_growth_pct))
            .replace("__SOURCES_NOTE__", sources_note)
            .replace("__DATA_JSON__", json.dumps(data_obj)))

    DASHBOARD_DIR.mkdir(exist_ok=True)
    out_path = DASHBOARD_DIR / f"{ticker}_dashboard.html"
    with open(out_path, "w") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    ticker_arg = sys.argv[1] if len(sys.argv) > 1 else "NKE"
    path = build_dashboard(ticker_arg)
    print(f"Dashboard written to {path}")
    print("Open it directly in a browser to view.")
