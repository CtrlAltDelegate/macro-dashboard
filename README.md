# Macro Dashboard

Private, local-first analytical dashboard for macro/market regime indicators. Produces newsletter-ready charts (exportable PNG) for Substack.

## Features

Four tabs, plus a readout strip, optional AI interpretation, Macro Drivers headlines and a one-page PDF summary.

- **Macro (Core)** — model-input cards grouped by theme (rates & inflation, growth & labor, liquidity & credit, market stress), each with its 1Y change and the date of the latest observation. Includes the Sahm rule, 10Y breakeven inflation, IG spread, VIX and the broad dollar. Charts are laid out two per row, with descriptions under "About this chart":
  1. Global Liquidity — Fed balance sheet (WALCL) YoY %, plus **net liquidity** (WALCL − Treasury General Account − reverse repo)
  2. Stock Market Pressure — `((SPX/UNRATE²) × CPI × FEDFUNDS) / M2`, rebased to 100
  3. Economic Risk Index — average of six pillar z-scores (3-year window), each oriented so higher = worse: real GDP growth, 1-year change in unemployment, CPI inflation, NFCI, Fed balance-sheet growth and HY spread; plus its 1-month ROC. Computed with 5 years of extra history so the start of every lookback is warmed up
  4. Yield Curve (10Y – 3M and 10Y – 2Y) + 90-day momentum
  5. Financial Conditions (Chicago Fed NFCI)
  6. Credit Spreads (ICE BofA high-yield and investment-grade OAS)
  7. Market Risk Level (0–100) — 1-year rolling percentile of the risk composite, in six zones (Very Low → Extreme) shared by every tab

  Time-series charts shade NBER recessions (FRED `USREC`; NBER announces dates with a lag).
- **Markets** — WTI oil (optional YoY / CPI YoY overlay), Bitcoin (optional liquidity / real-yield overlays), BTC weekly WMAs and a log-regression "rainbow". BTC metrics use full history; charts follow the lookback.
- **Regimes & Bands** — S&P 500, BTC and oil shaded by Market Risk Level zone (a zone change must hold ~2 weeks, so brief crossings don't flicker), plus the **Rotation Ladder** (z-scored ETH/BTC → BTC/SPY → SPY/GLD → GLD/TLT), or a FRED-only regime chart when Yahoo is unavailable.
- **Fiscal** — deficit % GDP, debt-to-GDP, net interest % GDP.

## Setup

1. **Clone / open project**, then:

   ```bash
   git clone https://github.com/CtrlAltDelegate/macro-dashboard.git
   cd macro-dashboard
   pip install -r requirements.txt
   ```

2. **FRED API key** (free):  
   [Create one](https://fred.stlouisfed.org/docs/api/api_key.html), then:

   - Create a `.env` file (copy from `.env.example`) and set:
     ```env
     FRED_API_KEY=your_key_here
     ```
   - Or set the `FRED_API_KEY` environment variable.

3. **Run the dashboard** (from the project root, i.e. the folder that contains `app.py`):

   ```bash
   streamlit run app.py
   ```

   Or run `python run_app.py` from anywhere inside the repo—it switches to the project root first.

   Open the URL shown (e.g. http://localhost:8501). Use **Refresh data** in the sidebar to refetch. Core charts have an **Export PNG** button (rendered on click via Kaleido, then **Download PNG**).

4. **Macro lookback** (sidebar): choose **1y**, **3y**, **5y**, **10y**, or **Max**; it applies to FRED data, the Rotation Ladder and chart display windows.

## Headless refresh (Tue/Fri export)

To re-fetch data and export PNGs without opening the app (e.g. for Task Scheduler):

```powershell
python refresh.py          # default 5y lookback
python refresh.py 10y       # optional: 1y, 3y, 5y, 10y, Max
```

Or run `scripts\refresh.ps1` from the project root. Output:

- **exports\\latest\\** — nine PNGs, `01_global_liquidity.png` … `09_net_liquidity.png` (see `EXPORT_NAMES` in `refresh.py`)
- **exports\\YYYY-MM-DD\\** — same files, dated for that run

The script exits with code 1 if no PNG could be written (e.g. missing FRED key or Kaleido), so Task Scheduler shows the failure.

**Windows Task Scheduler (Tue/Fri 7:00 AM):** see **[SCHEDULE.md](SCHEDULE.md)** for step-by-step setup.

## Data

- **Macro**: FRED (St. Louis Fed) — free with API key.
- **Rotation Ladder / BTC fallback**: Yahoo Finance — no key required. These still load when no FRED key is set.
- **Macro Drivers (news)**: RSS feeds (CNBC, MarketWatch, Yahoo Finance, BBC, NPR) — no key required.
- **AI Interpretation** (optional): OpenAI — set `OPENAI_API_KEY` in `.env` or Streamlit Secrets to enable. Uses **gpt-4o-mini** for low cost; output is cached by report date and signal hash.

## Tests

Offline (synthetic data, no API keys or network):

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

The suite covers the date-based YoY math, the risk model (warm-up, missing pillars, zones), net liquidity units, chart builders, and headless runs of `app.py` with and without a FRED key.

## Troubleshooting

- **"Main module does not exist" / FileNotFoundError when running Streamlit**  
  Streamlit must run with the **project root** as the current directory (the folder that contains `app.py`). From a terminal, `cd` into the cloned repo (e.g. `cd macro-dashboard`) and run `streamlit run app.py` there. Or use `python run_app.py`, which changes to the project root for you.

- **Streamlit Community Cloud — "directory … does not exist"**  
  The repo has **no subfolder** named `RiskCycle`. `app.py` is at the **root** of the repo. In Streamlit Cloud → your app → **Settings**: set **Main file path** to **`app.py`** (not `RiskCycle/app.py`). Leave **App root** blank or as the repo root. Add `FRED_API_KEY` under **Secrets** (see below).

- **Streamlit Cloud: FRED key in Secrets but app still says "not set"**  
  In **Settings → Secrets**, use a **root-level** key (no section). Example:
  ```toml
  FRED_API_KEY = "your_actual_key_here"
  ```
  Not under `[api]` or similar. The app reads from `st.secrets["FRED_API_KEY"]` and sets the env var so the data layer can use it. Save, then **Reboot** the app so it picks up the secret.

## GitHub + Netlify

- **Landing page**: The `landing/` folder is a static site (HTML/CSS) you can deploy to **Netlify**. Netlify hosts static files only—the live dashboard runs on your machine (or [Streamlit Community Cloud](https://share.streamlit.io/) if you host it there).
- **Deploy to Netlify**: Connect the repo; the repo’s `netlify.toml` runs `python scripts/build_landing.py` (writes the landing page into `public/`) and publishes **public**. No need for a `landing` folder in the repo—the build script embeds the page. If you have `landing/` pushed, the script copies from it instead.
- **In Netlify dashboard**: Leave **Base directory** blank. Build command and Publish directory are set in `netlify.toml`.
- **GitHub link**: `landing/index.html` and the app footer (`app.py`, search for `GitHub`) point to `https://github.com/CtrlAltDelegate/macro-dashboard`; change both if you fork.

## License

Private use. No warranty.
