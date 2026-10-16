# Macro Dashboard

[![tests](https://github.com/CtrlAltDelegate/macro-dashboard/actions/workflows/tests.yml/badge.svg)](https://github.com/CtrlAltDelegate/macro-dashboard/actions/workflows/tests.yml)

Private, local-first analytical dashboard for macro/market regime indicators. Produces newsletter-ready charts (exportable PNG) for Substack.

## Features

Four tabs, plus a readout strip, optional AI interpretation, Macro Drivers headlines and a PDF brief (summary, What changed table and four key charts; built when you click **Prepare PDF brief**).

- **What changed** — under the readout, each headline signal (risk level, net liquidity, curve spreads, credit spreads, VIX, CPI, Sahm rule, S&P 500, BTC, oil…) compared with the last Tue/Fri issue, 1 week or 1 month ago. Moves are ranked by how unusual they are for that series (vs. its typical move over the same span), colored by whether they add or reduce risk; the full table is in an expander. Computed from the data itself, so nothing needs to be stored between runs.

- **Macro (Core)** — model-input cards grouped by theme (rates & inflation, growth & labor, liquidity & credit, market stress & breadth), each with its 1Y change and the date of the latest observation. Includes the Sahm rule, 10Y breakeven inflation, 10Y term premium, 30Y mortgage rate, building permits, bank lending standards, IG spread, VIX, the broad dollar, copper/gold and equal-/cap-weight S&P 500. Charts are laid out two per row, with descriptions under "About this chart":
  1. Global Liquidity — Fed balance sheet (WALCL) YoY %, plus **net liquidity** (WALCL − Treasury General Account − reverse repo)
  2. Stock Market Pressure — `((SPX/UNRATE²) × CPI inflation (YoY) × FEDFUNDS) / M2`; 100 = average over the lookback
  3. Economic Risk Index — average of six pillar z-scores (3-year window), each oriented so higher = worse: real GDP growth, 1-year change in unemployment, CPI inflation, NFCI, Fed balance-sheet growth and HY spread; plus its 1-month ROC. Computed with 5 years of extra history so the start of every lookback is warmed up
  4. Yield Curve (10Y – 3M and 10Y – 2Y) + 90-day momentum
  5. Financial Conditions (Chicago Fed NFCI)
  6. Credit Spreads (ICE BofA high-yield and investment-grade OAS)
  7. Market Risk Level (0–100) — 1-year rolling percentile of the risk composite, in six zones (Very Low → Extreme) shared by every tab

  Time-series charts shade NBER recessions (FRED `USREC`; NBER announces dates with a lag).
- **Markets** — WTI oil (optional YoY / CPI YoY overlay), Bitcoin (optional liquidity / real-yield overlays), BTC weekly WMAs and a log-regression "rainbow". BTC metrics use full history; charts follow the lookback. **Growth & Breadth** charts copper/gold (growth vs. safety) and RSP/SPY (market breadth).
  - **Bitcoin Cycle Regression Model** — Fits historical bear-market loss % and bull-market gain multiple across completed 4-year halving cycles (regression on cycles 1–3), then projects the current cycle: live drawdown from cycle top, projected bottom band, days elapsed vs. historical bear durations, and a divergence flag comparing the current cycle's actual bull-market multiple to the model (n=3 — scenario anchor, not a forecast).
- **Regimes & Bands** — S&P 500, BTC and oil shaded by Market Risk Level zone (a zone change must hold ~2 weeks, so brief crossings don't flicker), plus the **Rotation Ladder** (z-scored ETH/BTC → BTC/SPY → SPY/GLD → GLD/TLT), or a FRED-only regime chart when Yahoo is unavailable.
  - **Historical Bear Markets (S&P 500 / NASDAQ)** — Algorithmic peak-to-trough drawdown detection (≥20%) over full price history, shown as a descriptive reference (shaded chart + table of past bear markets' depth/duration) alongside the current drawdown from all-time high. Unlike the BTC cycle model, this is **not** a regression or projection — equities lack a halving-equivalent fixed cadence, so past bear markets are shown as-is rather than extrapolated.
- **Fiscal** — deficit % GDP, debt-to-GDP, net interest % GDP.

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

Open the URL shown (e.g. `http://localhost:8501`). Use **Refresh data** in the sidebar to refetch. Core charts have an **Export PNG** button (rendered on click via Kaleido, then **Download PNG**).

**Macro lookback** (sidebar): choose **1y**, **3y**, **5y**, **10y**, or **Max**; it applies to FRED data, the Rotation Ladder and chart display windows.

---

## Chart export (PNG)

PNG export tries **Kaleido** first (`pip install -r requirements.txt` includes it), then **Playwright** if Kaleido fails.

- **Playwright Chromium** (only if needed): `pip install playwright` then `python -m playwright install chromium` (use `python -m` on Windows if `playwright` is not on PATH).

---

## PDF report

**Prepare PDF brief** (bottom of the page) builds a brief on demand: header, Today's Snapshot, the What changed table, Macro Radar, AI interpretation if enabled, Macro Drivers headlines, then four key charts (Net Liquidity, Economic Risk Index, Yield Curve, Market Risk Level). If PNG export (Kaleido) isn't available on the server, the charts are skipped with a note, so the PDF always builds.

---

## Headless refresh (Tue/Fri export)

Re-fetch data and export PNGs without opening the app (e.g. for Task Scheduler):

```powershell
python refresh.py          # default 5y lookback
python refresh.py 10y       # optional: 1y, 3y, 5y, 10y, Max
```

Or run `scripts\refresh.ps1` from the project root.

- **exports\\latest\\** — nine PNGs, `01_global_liquidity.png` … `09_net_liquidity.png` (see `EXPORT_NAMES` in `refresh.py`), plus `what_changed.md`: a table of what moved since the previous Tue/Fri issue, ready to paste into the newsletter
- **exports\\YYYY-MM-DD\\** — same files, dated for that run

The script exits with code 1 if no PNG could be written (e.g. missing FRED key or Kaleido), so Task Scheduler shows the failure.

**Windows Task Scheduler (Tue/Fri 7:00 AM):** see **[SCHEDULE.md](SCHEDULE.md)** for step-by-step setup.

## Data sources

- **Macro**: FRED (St. Louis Fed) — free with API key.
- **Rotation Ladder, copper/gold, RSP/SPY, BTC fallback, S&P 500 / NASDAQ history**: Yahoo Finance — no key required. The Yahoo-backed charts still load when no FRED key is set.
- **Macro Drivers (news)**: RSS feeds (CNBC, CNBC Economy, MarketWatch, Federal Reserve press releases, BBC, NPR) — no key required; cached for 15 minutes.
- **AI Interpretation** (optional): Anthropic Claude — set `CLAUDE_API_KEY` (or `ANTHROPIC_API_KEY`) in `.env` or Streamlit Secrets. Default model is **Claude Opus 5.5** (`claude-opus-5-5`, effort `medium`) with structured JSON output and server-side refusal fallback; if a model ID is retired it falls back to Claude Sonnet 5.5. Override with `CLAUDE_MODEL` (e.g. `claude-sonnet-5-5` or `claude-haiku-5-5` to save cost). Because the summary is cached per day and signal set, it typically costs a few cents a day. Output is cached by report date and signal hash. The prompt includes the current readings (net liquidity, 10Y–2Y, Sahm rule, IG spread, VIX, …) and the computed "What changed" moves, and the summary's "What changed" is limited to those moves rather than guessed.

## Tests

Offline (synthetic data, no API keys or network):

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

The suite covers the date-based YoY math, the risk model (warm-up, missing pillars, zones), net liquidity units, chart builders, the What changed signals, the AI prompt and model fallback (fake Anthropic client), the PDF, zone calibration, and headless runs of `app.py` with and without a FRED key. Network access is blocked during tests. GitHub Actions runs the suite on every push to `main` (`.github/workflows/tests.yml`).

## Zone calibration

Do the Market Risk Level zones actually separate stock-market outcomes? With a FRED key:

```bash
python scripts/calibrate_zones.py
```

computes the risk model over full history and, for each zone, the S&P 500's median forward 3/6/12-month returns, how often 12 months later was higher, and the average worst 6-month drawdown. Output goes to the console and `exports/zone_calibration.md`. Use it to sanity-check or adjust the cut-offs in `models/thermostat.py` (`RISK_ZONES`).

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

## KFH integration API (SummitPIC)

A separate FastAPI service (`api/`) implements the KFH Integration Spec so this dashboard
can plug into the Family Office Dashboard: `GET /health`, `GET /api/summary`, `GET /api/alerts`
+ `PATCH /api/alerts/:id`, `GET/POST /api/regime`, `/api/regime/history`, `/api/regime/evaluate`,
and full CRUD on `/api/signals` and `/api/indicators`. It runs independently of the Streamlit
app (its own process/port) and shares this repo's FRED data/model code to auto-seed a starter
set of macro signals (yield curve, credit spreads, NFCI, inflation, unemployment, GDP,
liquidity) — regime posture is then computed from whatever signals are currently stored,
auto-seeded or manually edited via the API.

### Run it

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

Interactive docs at `http://localhost:8000/docs`.

### Environment variables

```env
# Database — defaults to a local SQLite file if unset. Point at Supabase (or any) Postgres for prod.
DATABASE_URL=postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres

# JWT verification — pick ONE mode. Leave both unset for local dev (unsigned decode; not safe past localhost).
JWT_JWKS_URL=https://<issuer>/.well-known/jwks.json   # RS256, e.g. Clerk or Supabase Auth (asymmetric)
JWT_SECRET=<shared-secret>                             # HS256, e.g. Supabase Auth's project JWT secret
JWT_ISSUER=                                            # optional: verified if set
JWT_AUDIENCE=                                          # optional: verified if set

# CORS
DASHBOARD_ORIGIN=https://your-summitpic-domain.example
```

`user_id` is read from the JWT's `sub` claim (standard across both Clerk and Supabase Auth),
so switching issuers later is just an env var change.

---

## GitHub + Netlify

- **Landing page**: The `landing/` folder is a static site (HTML/CSS) you can deploy to **Netlify**. Netlify hosts static files only—the live dashboard runs on your machine (or [Streamlit Community Cloud](https://share.streamlit.io/) if you host it there).
- **Deploy to Netlify**: Connect the repo; the repo’s `netlify.toml` runs `python scripts/build_landing.py` (writes the landing page into `public/`) and publishes **public**. No need for a `landing` folder in the repo—the build script embeds the page. If you have `landing/` pushed, the script copies from it instead.
- **In Netlify dashboard**: Leave **Base directory** blank. Build command and Publish directory are set in `netlify.toml`.
- **GitHub link**: `landing/index.html` and the app footer (`app.py`, search for `GitHub`) point to `https://github.com/CtrlAltDelegate/macro-dashboard`; change both if you fork.

## License

Private use. No warranty.
