"""
Zone calibration: how did stocks do after each Market Risk Level zone?

For each week, take the risk zone and the S&P 500's forward returns / drawdown, then summarize by zone.
Used by scripts/calibrate_zones.py to check whether the zone cut-offs (RISK_ZONES) separate outcomes.

Caveats: FRED serves today's revised data, not what was known at the time (no vintages), and overlapping
forward windows mean the weekly observations are not independent — read the table as descriptive.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .thermostat import RISK_ZONES, risk_zone_index

HORIZONS = {"3M": pd.DateOffset(months=3), "6M": pd.DateOffset(months=6), "12M": pd.DateOffset(months=12)}


def forward_outcomes(prices: pd.Series, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Forward % returns over HORIZONS and the worst 6-month drawdown, for each date (NaN past the data end)."""
    p = prices.dropna().sort_index()
    out = pd.DataFrame(index=dates)
    start_px = p.asof(dates).to_numpy(dtype=float)
    for name, off in HORIZONS.items():
        ends = dates + off
        end_px = p.asof(ends).to_numpy(dtype=float, copy=True)  # writable (pandas copy-on-write)
        end_px[ends > p.index[-1]] = np.nan  # window not complete yet
        out[f"ret_{name}"] = (end_px / start_px - 1) * 100
    dd = []
    for d, px0 in zip(dates, start_px):
        end = d + HORIZONS["6M"]
        if end > p.index[-1] or np.isnan(px0):
            dd.append(np.nan)
            continue
        window = p[(p.index > d) & (p.index <= end)]
        dd.append((window.min() / px0 - 1) * 100 if len(window) else np.nan)
    out["maxdd_6M"] = dd
    return out


def zone_forward_stats(thermo: pd.Series, prices: pd.Series, freq: str = "W-FRI") -> pd.DataFrame:
    """One row per risk zone (plus 'All'): weeks observed, median forward returns, % of positive 12M
    outcomes, and the average worst 6M drawdown."""
    weekly = thermo.dropna().resample(freq).last().dropna()
    if weekly.empty:
        return pd.DataFrame()
    outcomes = forward_outcomes(prices, weekly.index)
    outcomes["zone"] = [RISK_ZONES[risk_zone_index(v)][2] for v in weekly.to_numpy()]

    def summarize(g: pd.DataFrame) -> dict:
        return {
            "weeks": len(g),
            **{f"median {h} %": g[f"ret_{h}"].median() for h in HORIZONS},
            "12M positive %": (g["ret_12M"].dropna() > 0).mean() * 100 if g["ret_12M"].notna().any() else np.nan,
            "avg worst 6M drawdown %": g["maxdd_6M"].mean(),
        }

    rows = {label: summarize(outcomes[outcomes["zone"] == label]) for _lo, _hi, label in RISK_ZONES}
    rows["All"] = summarize(outcomes)
    table = pd.DataFrame(rows).T
    return table[table["weeks"] > 0]


def stats_markdown(table: pd.DataFrame, title: str) -> str:
    """Render zone_forward_stats() as a markdown table."""
    cols = list(table.columns)
    lines = [f"# {title}", "", "| Zone | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for zone, row in table.iterrows():
        cells = [f"{int(row[c])}" if c == "weeks" else ("-" if pd.isna(row[c]) else f"{row[c]:.1f}") for c in cols]
        lines.append(f"| {zone} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
