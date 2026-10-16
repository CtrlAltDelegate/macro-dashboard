"""
Calendar-based change helpers.

FRED series of different frequencies are merged and forward-filled onto a common (usually daily)
index, so row-count lookbacks like shift(12) do NOT mean "12 months". These helpers look back by
calendar time instead, which is correct for any frequency.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ONE_YEAR = pd.Timedelta(days=365)
# Extra history to fetch so a YoY series covers the whole display window. A year plus a margin: monthly and
# quarterly series' first observation can fall weeks after the fetch start.
YOY_FETCH_MARGIN = pd.DateOffset(years=1, days=100)


def yoy_fetch_start(display_start: str | None) -> str | None:
    """Fetch start for series shown as year-over-year changes from display_start (None = full history)."""
    return (pd.Timestamp(display_start) - YOY_FETCH_MARGIN).date().isoformat() if display_start else None


def change_over(series: pd.Series, lookback: pd.Timedelta = ONE_YEAR, *, pct: bool = True) -> pd.Series:
    """Change vs. the last value at or before (date - lookback). pct=True → % change, else difference."""
    s = series.dropna()
    if s.empty:
        return pd.Series(dtype=float)
    past = pd.Series(s.asof(s.index - lookback).to_numpy(dtype=float), index=s.index)
    out = (s - past) / past.abs() * 100 if pct else s - past
    return out.replace([np.inf, -np.inf], np.nan).dropna()


def latest_change(series: pd.Series | None, lookback: pd.Timedelta = ONE_YEAR, *, pct: bool = True) -> float | None:
    """Most recent value of change_over(); None if there is not enough history."""
    if series is None:
        return None
    s = series.dropna()
    if len(s) < 2:
        return None
    new = s.iloc[-1]
    old = s.asof(s.index[-1] - lookback)
    if pd.isna(old) or (pct and old == 0):
        return None
    return float((new - old) / abs(old) * 100 if pct else new - old)
