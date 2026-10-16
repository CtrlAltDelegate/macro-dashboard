"""
Chart 1 — Valuation Pressure Index ("Stock Market Pressure").

Formula: ((SPX / UNRATE^2) × CPI inflation (YoY %) × FEDFUNDS) / M2

Rising = macro tightening / pressure building.
Falling = liquidity improving / pressure easing.

Inflation enters as the year-over-year rate, not the CPI level: the level rises for decades, which
would inflate the index by the price level alone. Deflation is floored at 0 (no inflation pressure).
SPX / M2 stays a ratio of levels (equities relative to the money stock).
"""
from __future__ import annotations

import pandas as pd

from .timeseries import change_over


def compute_valuation_pressure_index(df: pd.DataFrame) -> pd.Series:
    """
    Compute valuation pressure from DataFrame with columns:
    SP500, UNRATE, INFLATION (CPI level, e.g. CPIAUCSL), FEDFUNDS, M2 (e.g. M2SL).
    Needs a year of CPI history before the first output date (for the YoY rate).
    Mixed frequencies are aligned by forward-filling each series onto the common index.
    """
    inflation = change_over(df["INFLATION"]).clip(lower=0)
    aligned = df.drop(columns=["INFLATION"]).assign(INFLATION=inflation).ffill()
    unr2 = (aligned["UNRATE"] ** 2).replace(0, pd.NA)  # UNRATE in percent (e.g. 4.0)
    numerator = (aligned["SP500"] / unr2) * aligned["INFLATION"] * aligned["FEDFUNDS"]
    return (numerator / aligned["M2"]).dropna().astype(float)


def rebase_to_window_mean(index: pd.Series) -> pd.Series:
    """Scale so the window's average = 100. (Rebasing to the first value breaks when the window starts
    near zero rates, e.g. fed funds at 0.08% in 2021 made later values look 60x higher.)"""
    mean = index.mean()
    return index / mean * 100 if mean and pd.notna(mean) else index
