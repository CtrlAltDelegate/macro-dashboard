"""
Chart 1 — Valuation Pressure Index.

Formula: ((SPX / UNRATE^2) × INFLATION × FEDFUNDS) / M2

Rising = macro tightening / pressure building.
Falling = liquidity improving / pressure easing.

Note: INFLATION (CPI) and M2 are level series; for long lookbacks consider
using YoY % change to keep the index stable. Chart display rebases to 100 at start.
"""
from __future__ import annotations

import pandas as pd


def compute_valuation_pressure_index(df: pd.DataFrame) -> pd.Series:
    """
    Compute valuation pressure from DataFrame with columns:
    SP500, UNRATE, INFLATION (e.g. CPIAUCSL), FEDFUNDS, M2 (e.g. M2SL).
    """
    spx = df["SP500"]
    unr = df["UNRATE"]
    inf = df["INFLATION"]
    ff = df["FEDFUNDS"]
    m2 = df["M2"]

    # Avoid division by zero; UNRATE in percent (e.g. 4.0)
    unr2 = (unr ** 2).replace(0, pd.NA)
    numerator = (spx / unr2) * inf * ff
    index = numerator / m2
    return index.dropna()
