"""
Headless refresh: fetch data, recompute indicators, export newsletter-ready PNGs.
Run directly (e.g. python refresh.py) or via scripts/refresh.ps1 / Task Scheduler.
Output: exports/YYYY-MM-DD/ and exports/latest/
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Load .env before importing config (so FRED_API_KEY is set)
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import config
from data import fetch_valuation_data, fetch_macro_risk_data, fetch_yield_curve_data, fetch_rotation_data
from charts.build import build_all_charts

# Descriptive filenames for Substack / newsletter
EXPORT_NAMES = [
    "01_valuation_pressure_index.png",
    "02_macro_risk_raw_roc.png",
    "03_yield_curve_10y_3m.png",
    "04_market_risk_level.png",
    "05_risk_cascade_rotation.png",
]


def run_refresh(lookback: str = "5y") -> int:
    """
    Pull FRED + market data, recompute charts, export to exports/YYYY-MM-DD/ and exports/latest/.
    Returns 0 on success, 1 on failure.
    """
    if not config.FRED_API_KEY:
        print("FRED_API_KEY not set. Set it in .env or environment.", file=sys.stderr)
        return 1

    obs_start = config.lookback_to_observation_start(lookback)
    rot_period = config.lookback_to_rotation_period(lookback)

    print("Fetching FRED (valuation + macro risk + yield curve)...")
    try:
        val_df = fetch_valuation_data(observation_start=obs_start)
        risk_df = fetch_macro_risk_data(observation_start=obs_start)
        yield_df = fetch_yield_curve_data(observation_start=obs_start)
    except Exception as e:
        print(f"FRED fetch failed: {e}", file=sys.stderr)
        return 1

    print("Fetching rotation data (Yahoo Finance)...")
    try:
        rot_df = fetch_rotation_data(period=rot_period)
    except Exception as e:
        print(f"Rotation fetch failed: {e}", file=sys.stderr)
        rot_df = pd.DataFrame()

    print("Building charts...")
    figs = build_all_charts(val_df, risk_df, yield_df, rot_df)

    today = date.today().isoformat()
    date_dir = config.EXPORTS_DIR / today
    latest_dir = config.EXPORTS_DIR / "latest"
    date_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    for fig, name in zip(figs, EXPORT_NAMES):
        if fig is None:
            print(f"  Skip {name} (insufficient data)")
            continue
        for folder in (date_dir, latest_dir):
            path = folder / name
            try:
                fig.write_image(str(path), format="png", scale=2)
                print(f"  Wrote {path.relative_to(config.PROJECT_ROOT)}")
            except Exception as e:
                print(f"  Failed {path}: {e}", file=sys.stderr)

    print(f"Done. Exports: {date_dir}, {latest_dir}")
    return 0


if __name__ == "__main__":
    lookback = sys.argv[1] if len(sys.argv) > 1 else "5y"
    sys.exit(run_refresh(lookback=lookback))
