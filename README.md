# Macro Dashboard

Private, local-first analytical dashboard for macro/market regime indicators. Produces newsletter-ready charts (exportable PNG) for Substack.

## Features

- **Chart 1 — Valuation Pressure Index**  
  `((SPX/UNRATE²) × INFLATION × FEDFUNDS) / M2`  
  Rising = macro tightening; falling = easing.

- **Chart 2 — Macro Risk Dashboard**  
  Raw standardized composite + ROC (acceleration). Pillars: GDP, unemployment, inflation, NFCI, Fed liquidity, HY spread.

- **Chart 3 — Risk Thermostat (0–100)**  
  Allocation guide: Risk-on → Neutral → De-risk → Defensive → Capital preservation.

- **Chart 4 — Risk Cascade Curves**  
  Relative strength ratios (ALT/BTC, BTC/SPY, IWM/SPY, HYG/IEF, XLU/SPY) to detect rotation order.

## Setup

1. **Clone / open project**, then:

   ```bash
   cd RiskCycle
   pip install -r requirements.txt
   ```

2. **FRED API key** (free):  
   [Create one](https://fred.stlouisfed.org/docs/api/api_key.html), then:

   - Create a `.env` file (copy from `.env.example`) and set:
     ```env
     FRED_API_KEY=your_key_here
     ```
   - Or set the `FRED_API_KEY` environment variable.

3. **Run the dashboard**:

   ```bash
   streamlit run app.py
   ```

   Open the URL shown (e.g. http://localhost:8501). Use **Refresh data** in the sidebar to refetch; each chart has an **Export chart as PNG** button.

4. **Macro lookback** (sidebar): choose **1y**, **3y**, **5y**, **10y**, or **Max**; it applies to FRED data and rotation window.

## Headless refresh (Tue/Fri export)

To re-fetch data and export PNGs without opening the app (e.g. for Task Scheduler):

```powershell
python refresh.py          # default 5y lookback
python refresh.py 10y       # optional: 1y, 3y, 5y, 10y, Max
```

Or run `scripts\refresh.ps1` from the project root. Output:

- **exports\\latest\\** — four PNGs: `01_valuation_pressure_index.png`, `02_macro_risk_raw_roc.png`, `03_risk_thermostat.png`, `04_risk_cascade_rotation.png`
- **exports\\YYYY-MM-DD\\** — same files, dated for that run

**Windows Task Scheduler (Tue/Fri 7:00 AM):** see **[SCHEDULE.md](SCHEDULE.md)** for step-by-step setup.

## Data

- **Macro**: FRED (St. Louis Fed) — free with API key.
- **Rotation (Chart 4)**: Yahoo Finance — no key required.

## GitHub + Netlify

- **Landing page**: The `landing/` folder is a static site (HTML/CSS) you can deploy to **Netlify**. Netlify hosts static files only—the live dashboard runs on your machine (or [Streamlit Community Cloud](https://share.streamlit.io/) if you host it there).
- **Deploy to Netlify**: Connect the repo; the repo’s `netlify.toml` runs `python scripts/build_landing.py` (writes the landing page into `public/`) and publishes **public**. No need for a `landing` folder in the repo—the build script embeds the page. If you have `landing/` pushed, the script copies from it instead.
- **In Netlify dashboard**: Leave **Base directory** blank. Build command and Publish directory are set in `netlify.toml`.
- **Update GitHub link**: In `landing/index.html`, replace `https://github.com` with your repo URL (e.g. `https://github.com/CtrlAltDelegate/macro-dashboard`). In the Streamlit app, the footer link can be changed in `app.py` (search for `GitHub`).

## License

Private use. No warranty.
