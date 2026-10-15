"""
Headless refresh: fetch data, recompute indicators, export newsletter-ready PNGs.
Run directly (e.g. python refresh.py) or via scripts/refresh.ps1 / Task Scheduler.
Output: exports/YYYY-MM-DD/ and exports/latest/
"""
from __future__ import annotations

import sys
from datetime import date

# Load .env before importing config (so FRED_API_KEY is set)
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import config
from data import (
    fetch_valuation_data,
    fetch_macro_risk_data,
    fetch_yield_curve_data,
    fetch_liquidity_data,
    fetch_rotation_ladder_data,
    fetch_recession_periods,
    fetch_model_input_series,
)
from charts.build import build_all_charts, add_recession_shading
from models import compute_risk_model, warmup_start

# Descriptive filenames for Substack / newsletter (order matches dashboard 1–8)
EXPORT_NAMES = [
    "01_global_liquidity.png",
    "02_stock_market_pressure.png",
    "03_economic_risk_index.png",
    "04_yield_curve_10y_3m.png",
    "05_financial_conditions_index.png",
    "06_credit_spreads.png",
    "07_market_risk_level.png",
    "08_rotation_ladder.png",
    "09_net_liquidity.png",
]


def run_refresh(lookback: str = "5y") -> int:
    """
    Pull FRED + market data, recompute charts, export to exports/YYYY-MM-DD/ and exports/latest/.
    Returns 0 if at least one PNG was written, 1 otherwise.
    """
    if lookback not in config.LOOKBACK_OPTIONS:
        print(f"Unknown lookback {lookback!r}; use one of {', '.join(config.LOOKBACK_OPTIONS)}", file=sys.stderr)
        return 1
    if not config.FRED_API_KEY:
        print("FRED_API_KEY not set. Set it in .env or environment.", file=sys.stderr)
        return 1

    obs_start = config.lookback_to_observation_start(lookback)

    print("Fetching FRED (valuation + macro risk + yield curve + liquidity)...")
    try:
        val_df = fetch_valuation_data(observation_start=obs_start)
        risk_full = fetch_macro_risk_data(observation_start=warmup_start(obs_start))
        yield_df = fetch_yield_curve_data(observation_start=obs_start)
        # A year of extra history so the YoY line covers the whole window
        liq_start = (pd.Timestamp(obs_start) - pd.DateOffset(years=1)).date().isoformat() if obs_start else None
        liquidity_df = fetch_liquidity_data(observation_start=liq_start)
        ig_series = fetch_model_input_series(observation_start=obs_start).get("BAMLC0A0CM")  # optional; empty on failure
        recessions = fetch_recession_periods(observation_start=obs_start)
    except Exception as e:
        print(f"FRED fetch failed: {e}", file=sys.stderr)
        return 1

    print("Fetching rotation ladder data (Yahoo Finance)...")
    try:
        ladder_df = fetch_rotation_ladder_data(start=obs_start)
    except Exception as e:
        print(f"Rotation fetch failed (falling back to FRED-only regime chart): {e}", file=sys.stderr)
        ladder_df = pd.DataFrame()

    print("Building charts...")
    risk_df = risk_full[risk_full.index >= pd.Timestamp(obs_start)] if obs_start else risk_full
    composite, thermo = compute_risk_model(risk_full, obs_start)
    figs = build_all_charts(
        val_df, risk_df, yield_df, liquidity_df, ladder_df,
        show_event_markers=False, composite=composite, thermo=thermo,
        display_start=obs_start, ig_series=ig_series,
    )
    for fig in figs:
        add_recession_shading(fig, recessions)

    today = date.today().isoformat()
    date_dir = config.EXPORTS_DIR / today
    latest_dir = config.EXPORTS_DIR / "latest"
    date_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    from plotly_export import export_plotly_to_png_or_error

    written = 0
    for fig, name in zip(figs, EXPORT_NAMES):
        if fig is None:
            print(f"  Skip {name} (insufficient data)")
            continue
        png, err = export_plotly_to_png_or_error(fig, width=800, height=450)
        if png is None:
            print(f"  Failed {name}: {err}", file=sys.stderr)
            continue
        for folder in (date_dir, latest_dir):
            path = folder / name
            try:
                path.write_bytes(png)
                print(f"  Wrote {path.relative_to(config.PROJECT_ROOT)}")
                written += 1
            except Exception as e:
                print(f"  Failed {path}: {e}", file=sys.stderr)

    if not written:
        print("No PNGs were written.", file=sys.stderr)
        return 1
    print(f"Done. Exports: {date_dir}, {latest_dir}")
    return 0


if __name__ == "__main__":
    lookback = sys.argv[1] if len(sys.argv) > 1 else "5y"
    sys.exit(run_refresh(lookback=lookback))
