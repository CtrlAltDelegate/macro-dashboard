"""
Chart 2 — Macro Risk Dashboard (raw standardized composite + ROC composite).

Pillars: GDP, Unemployment, Inflation, Credit Tightening (NFCI), Liquidity, Credit Stress.
Rising composite = macro deterioration; falling = stabilization.

Each pillar is first turned into a stationary signal (trending levels like CPI or the Fed balance
sheet become year-over-year changes), z-scored over a rolling calendar window at its own native
frequency, oriented so that higher = worse, and then averaged across the pillars available on each date.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .timeseries import change_over

# Rolling window for pillar z-scores (calendar time, so it means the same for daily/weekly/monthly data)
ZSCORE_WINDOW = pd.Timedelta(days=3 * 365)
# Fewest pillars that must be present on a date for the composite to be defined
MIN_PILLARS = 3
# History the composite + thermostat need before the first displayed date:
# 1y for YoY transforms + z-score window + 1y thermostat percentile window.
WARMUP = pd.DateOffset(years=5)

# column: (transform, higher_is_worse)
#   "yoy"  = % change vs. 1y ago (for trending levels)
#   "diff" = change vs. 1y ago in the series' own units (e.g. unemployment rate, pp)
#   "level" = already stationary
PILLARS: dict[str, tuple[str, bool]] = {
    "GDP": ("yoy", False),               # real GDP growth; faster growth = less risk
    "UNEMPLOYMENT": ("diff", True),      # rising unemployment = more risk
    "INFLATION": ("yoy", True),          # CPI inflation
    "CREDIT_TIGHTENING": ("level", True),  # NFCI: positive = tighter than average
    "LIQUIDITY": ("yoy", False),         # Fed balance sheet growth; expanding = less risk
    "CREDIT_STRESS": ("level", True),    # HY OAS
}


def _transform(series: pd.Series, how: str) -> pd.Series:
    s = series.dropna()
    if how == "yoy":
        return change_over(s)
    if how == "diff":
        return change_over(s, pct=False)
    return s


def _standardize(series: pd.Series, window: pd.Timedelta = ZSCORE_WINDOW) -> pd.Series:
    """Rolling z-score over a calendar window (needs ~1/3 of the window filled before it reports)."""
    if series.empty:
        return series
    span_days = (series.index[-1] - series.index[0]).days or 1
    obs_per_window = len(series) * window.days / span_days
    roll = series.rolling(window, min_periods=max(4, int(obs_per_window / 3)))
    return ((series - roll.mean()) / roll.std().replace(0, np.nan)).dropna()


def compute_pillar_scores(df: pd.DataFrame) -> pd.DataFrame:
    """One column per available pillar: risk-oriented z-score, forward-filled onto df's index."""
    cols = {}
    for name, (how, higher_is_worse) in PILLARS.items():
        if name not in df.columns:
            continue
        z = _standardize(_transform(df[name], how))
        if z.empty:
            continue
        cols[name] = z if higher_is_worse else -z
    if not cols:
        return pd.DataFrame()
    idx = df.index.sort_values()
    # Each pillar keeps its latest reading until the next release
    return pd.DataFrame({k: v.reindex(idx).ffill() for k, v in cols.items()})


def compute_macro_risk_composite(df: pd.DataFrame) -> pd.Series:
    """
    Raw standardized composite: mean of the available pillar z-scores (higher = worse).
    Dates with fewer than MIN_PILLARS pillars are dropped rather than averaged with zeros.
    """
    pillars = compute_pillar_scores(df)
    if pillars.empty:
        return pd.Series(dtype=float)
    composite = pillars.mean(axis=1, skipna=True).where(pillars.notna().sum(axis=1) >= MIN_PILLARS)
    return composite.replace([np.inf, -np.inf], np.nan).dropna()


def compute_risk_model(
    risk_df: pd.DataFrame,
    display_start: str | None = None,
) -> tuple[pd.Series, pd.Series]:
    """(composite, thermostat) computed on the full history, then trimmed to display_start.

    Fetch risk_df from warmup_start(display_start) so the first displayed values are fully warmed up.
    """
    from .thermostat import compute_risk_thermostat

    composite = compute_macro_risk_composite(risk_df)
    thermo = compute_risk_thermostat(composite)
    if display_start:
        start = pd.Timestamp(display_start)
        composite, thermo = composite[composite.index >= start], thermo[thermo.index >= start]
    return composite, thermo


def warmup_start(display_start: str | None) -> str | None:
    """Fetch start for risk data: display start minus WARMUP (None = full history)."""
    if not display_start:
        return None
    return (pd.Timestamp(display_start) - WARMUP).date().isoformat()


def compute_macro_risk_roc(
    composite: pd.Series,
    period: pd.Timedelta = pd.Timedelta(days=30),
) -> pd.Series:
    """ROC (change vs. one month earlier) of the raw composite for acceleration detection."""
    if composite.empty:
        return pd.Series(dtype=float)
    return change_over(composite, period, pct=False)
