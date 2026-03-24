# Macro Dashboard

Private, local-first analytical dashboard for macro/market regime indicators. Produces newsletter-ready charts (exportable PNG) for Substack.

## Features

The dashboard is organized into four tabs:

### Macro (Core)
- **Valuation Pressure Index** — `((SPX/UNRATE²) × INFLATION × FEDFUNDS) / M2`. Rising = macro tightening; falling = easing.
- **Macro Risk Dashboard** — Standardized composite + rate-of-change (acceleration). Pillars: GDP, unemployment, inflation, NFCI, Fed liquidity, HY spread.
- **Risk Thermostat (0–100)** — Allocation guide from risk-on → neutral → de-risk → defensive → capital preservation.
- **Yield Curve** — 10Y–3M spread with optional individual rate overlays and event markers.
- **Global Liquidity** — Fed balance sheet (WALCL) YoY.

### Markets
- **WTI Oil** — Spot price with optional YoY % and CPI overlay. Log scale toggle.
- **Bitcoin** — Price with optional liquidity YoY and real yield (10Y TIPS) overlays. Log scale toggle.
- **BTC Rainbow Bands** — Log-regression price channel with adjustable band width (σ).

### Regimes & Bands
- **SPX Regime Bands** — S&P 500 regime overlays with optional log scale.
- **Financial Conditions Index** — Chicago Fed NFCI.
- **Credit Spreads** — ICE BofA US HY OAS.
- **Rotation Ladder** — Z-score normalized ratios: ETH/BTC → BTC/SPX → SPX/Gold → Gold/Bonds. Detects rotation order from risk-on to defensive.
- **Risk Cascade Curves** — Relative strength ratios: ALT/BTC, BTC/SPY, IWM/SPY, HYG/IEF, XLU/SPY.

### Fiscal
- **Deficit % GDP** — Federal surplus/deficit as % of GDP.
- **Debt % GDP** — Federal debt as % of GDP.
- **Interest Burden** — Net interest outlays as % of GDP.

### Sidebar controls
- **Macro lookback**: 1y, 3y, 5y, 10y, Max — applies to FRED data and rotation window.
- **S&P 500 overlay** on Macro charts.
- Individual toggles for yield curve lines, event markers, oil and BTC overlays.
- **AI Interpretation** — AI-generated executive summary (optional; requires `CLAUDE_API_KEY` or `ANTHROPIC_API_KEY`).
- **Macro Drivers headlines** — 3–5 recent macro-relevant headlines from RSS feeds.
- **Refresh data** button.

---

## Setup

### 1. Install dependencies

```bash
git clone https://github.com/CtrlAltDelegate/macro-dashboard.git
cd macro-dashboard
pip install -r requirements.txt
```

### 2. FRED API key (free)

[Create one here](https://fred.stlouisfed.org/docs/api/api_key.html), then add it to a `.env` file in the project root (create the file if needed):

```env
FRED_API_KEY=your_key_here
```

Or set it as an environment variable directly.

**Optional — AI interpretation (local):** add to `.env`:

```env
CLAUDE_API_KEY=your_anthropic_key
```

(`ANTHROPIC_API_KEY` is also accepted.) On **Streamlit Cloud**, add the same keys under **Settings → Secrets** (root-level, like `FRED_API_KEY`).

### 3. Run the dashboard

From the **project root** (the folder containing `app.py`):

```bash
streamlit run app.py
```

If `streamlit` is not on your PATH (common on Windows):

```bash
python -m streamlit run app.py
```

Or:

```bash
python run_app.py
```

Open the URL shown (e.g. `http://localhost:8501`). Each chart has an **Export chart as PNG** button when data is available.

---

## Chart export (PNG)

PNG export tries **Kaleido** first (`pip install -r requirements.txt` includes it), then **Playwright** if Kaleido fails.

- **Playwright Chromium** (only if needed): `pip install playwright` then `python -m playwright install chromium` (use `python -m` on Windows if `playwright` is not on PATH).

---

## PDF report

**Download PDF** generates a **summary brief** (header, Today’s Snapshot, Macro Radar when available, AI interpretation if enabled, Macro Drivers headlines, footer). **Chart images are not embedded** in the PDF so export always works without extra setup. For chart visuals, use the dashboard and **Export chart as PNG** on each chart.

---

## Headless refresh (Tue/Fri export)

Re-fetch data and export PNGs without opening the app (e.g. for Task Scheduler):

```powershell
python refresh.py          # default 5y lookback
python refresh.py 10y       # optional: 1y, 3y, 5y, 10y, Max
```

Or run `scripts\refresh.ps1` from the project root.

**Output** (eight PNGs per run, mirrored to `latest` and dated folder):

- `01_global_liquidity.png` … `08_risk_cascade_rotation.png` (see `refresh.py` → `EXPORT_NAMES` for the full list)
- `exports\latest\` and `exports\YYYY-MM-DD\`

**Windows Task Scheduler (Tue/Fri 7:00 AM):** see [SCHEDULE.md](SCHEDULE.md) for step-by-step setup.

---

## Data sources

| Source | Used for | Key required? |
|--------|----------|---------------|
| FRED (St. Louis Fed) | All macro data | Yes — free at fred.stlouisfed.org |
| Yahoo Finance | Rotation charts (ETFs, BTC, ETH) | No |
| RSS feeds (CNBC, MarketWatch, Yahoo Finance, BBC, NPR) | Macro Drivers headlines | No |
| Anthropic Claude (optional) | AI interpretation summary | Yes — set `CLAUDE_API_KEY` or `ANTHROPIC_API_KEY` in `.env` or Streamlit Secrets |

Default model is **claude-haiku-4-5** (with automatic fallbacks if a model ID is retired). Override with env `CLAUDE_MODEL`. Output is cached by report date and signal hash.

---

## Troubleshooting

**"Main module does not exist" / FileNotFoundError**
Streamlit must run from the project root (the folder containing `app.py`). `cd` into the repo, then `streamlit run app.py`, `python -m streamlit run app.py`, or `python run_app.py`.

**Streamlit Community Cloud — "directory … does not exist"**
`app.py` is at the repo root — there is no `RiskCycle/` subfolder. In Streamlit Cloud → your app → **Settings**: set **Main file path** to `app.py`. Leave **App root** blank.

**Streamlit Cloud: FRED key in Secrets but app still says "not set"**
In **Settings → Secrets**, use a root-level key (no section header):
```toml
FRED_API_KEY = "your_actual_key_here"
```
Not under `[api]` or any other section. After saving, click **Reboot** the app.

**AI shows “unavailable” on Cloud but works locally**  
Add `CLAUDE_API_KEY` (or `ANTHROPIC_API_KEY`) to Secrets the same way as `FRED_API_KEY`, then reboot. Local runs need the key in `.env` or environment variables — Cloud secrets are not used on your PC.

---

## GitHub + Netlify

- **Landing page**: The `landing/` folder is a static site (HTML/CSS) deployable to Netlify. The live dashboard runs separately (local machine or Streamlit Community Cloud).
- **Deploy to Netlify**: Connect the repo. `netlify.toml` runs `python scripts/build_landing.py` (writes the page into `public/`) and publishes `public/`. Leave **Base directory** blank in Netlify.
- **Update GitHub link**: In `landing/index.html`, replace the placeholder GitHub URL with your repo URL. The footer link in the Streamlit app can be changed in `app.py` (search for `GitHub`).

---

## License

Private use. No warranty.
