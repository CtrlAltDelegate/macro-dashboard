"""
Chart 2 — Macro Risk Dashboard (raw standardized composite + ROC composite).

Pillars: GDP, Unemployment, Inflation, Credit Tightening (NFCI), Liquidity, Credit Stress.
Rising composite = macro deterioration; falling = stabilization.
"""
from __future__ import annotations

import pandas as pd
import numpy as np


def _standardize(series: pd.Series, window: int = 252) -> pd.Series:
    """Z-score over rolling window; for GDP/liquidity we invert so higher = worse."""
    roll = series.rolling(window, min_periods=min(60, window))
    return (series - roll.mean()) / roll.std().replace(0, np.nan)


def _orient_risk(s: pd.Series, higher_is_worse: bool) -> pd.Series:
    """Ensure higher value = higher macro risk (deterioration)."""
    if higher_is_worse:
        return s
    return -s


def compute_macro_risk_composite(
    df: pd.DataFrame,
    window: int = 252,
) -> pd.Series:
    """
    Raw standardized composite. Pillars: GDP, UNEMPLOYMENT, INFLATION,
    CREDIT_TIGHTENING (NFCI), LIQUIDITY (Fed balance sheet), CREDIT_STRESS (HY spread).
    Higher pillar value = worse for risk in all cases after orientation.
    """
    # Align to common index (forward-fill then dropna for date alignment)
    aligned = df.ffill().dropna(how="all")
    if aligned.empty or len(aligned) < 2:
        return pd.Series(dtype=float)

    out = pd.Series(0.0, index=aligned.index)
    count = 0

    # GDP: higher = better → invert so higher composite = worse
    if "GDP" in aligned.columns:
        g = aligned["GDP"].dropna()
        if len(g) > 0:
            out = out.add(_orient_risk(_standardize(g, window), higher_is_worse=False), fill_value=0)
            count += 1
    # Unemployment: higher = worse
    if "UNEMPLOYMENT" in aligned.columns:
        u = aligned["UNEMPLOYMENT"].dropna()
        if len(u) > 0:
            out = out.add(_orient_risk(_standardize(u, window), higher_is_worse=True), fill_value=0)
            count += 1
    # Inflation: higher = worse
    if "INFLATION" in aligned.columns:
        i = aligned["INFLATION"].dropna()
        if len(i) > 0:
            out = out.add(_orient_risk(_standardize(i, window), higher_is_worse=True), fill_value=0)
            count += 1
    # NFCI: higher = tighter = worse
    if "CREDIT_TIGHTENING" in aligned.columns:
        n = aligned["CREDIT_TIGHTENING"].dropna()
        if len(n) > 0:
            out = out.add(_orient_risk(_standardize(n, window), higher_is_worse=True), fill_value=0)
            count += 1
    # Liquidity (Fed balance sheet): higher = more liquidity = better → invert
    if "LIQUIDITY" in aligned.columns:
        lq = aligned["LIQUIDITY"].dropna()
        if len(lq) > 0:
            out = out.add(_orient_risk(_standardize(lq, window), higher_is_worse=False), fill_value=0)
            count += 1
    # Credit stress (HY spread): higher = worse
    if "CREDIT_STRESS" in aligned.columns:
        c = aligned["CREDIT_STRESS"].dropna()
        if len(c) > 0:
            out = out.add(_orient_risk(_standardize(c, window), higher_is_worse=True), fill_value=0)
            count += 1

    if count == 0:
        return pd.Series(dtype=float)
    composite = out / count
    return composite.replace([np.inf, -np.inf], np.nan).dropna()


def compute_macro_risk_roc(
    composite: pd.Series,
    period: int = 21,
) -> pd.Series:
    """ROC (rate of change) of the raw composite for acceleration detection."""
    if composite.empty or len(composite) < period + 1:
        return pd.Series(dtype=float)
    roc = composite.diff(period)
    return roc.dropna()
