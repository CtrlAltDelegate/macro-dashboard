"""
Chart 4 — Risk Cascade Curves (rotation engine).

Relative strength ratios to see which asset breaks first:
ALT/BTC, BTC/SPY, IWM/SPY, HYG/IEF, XLU/SPY.
Normalized (e.g. rebased to 100) for comparable curves.
"""
from __future__ import annotations

import pandas as pd
import numpy as np


def prepare_rotation_zscore(ratios_df: pd.DataFrame, window: int | None = None) -> pd.DataFrame:
    """
    Z-score normalize each ratio column so they are comparable on one chart.
    window=None uses full-sample mean/std; otherwise rolling(window).
    """
    if ratios_df.empty:
        return ratios_df
    out = pd.DataFrame(index=ratios_df.index)
    for col in ratios_df.columns:
        s = ratios_df[col].dropna()
        if s.empty or len(s) < 2:
            continue
        if window is None or window >= len(s):
            mean, std = s.mean(), s.std()
            if std == 0 or np.isnan(std):
                out[col] = 0.0
            else:
                out[col] = (s - mean) / std
        else:
            roll = s.rolling(window, min_periods=max(2, window // 2))
            out[col] = (s - roll.mean()) / roll.std().replace(0, np.nan)
    return out.dropna(how="all").ffill().dropna(how="all")


def prepare_rotation_curves(ratios_df: pd.DataFrame, base_date: str | None = None) -> pd.DataFrame:
    """
    Take ratio series and rebase each to 100 at base_date (or first valid date).
    Returns DataFrame with same columns, values as index levels (100 = start).
    """
    if ratios_df.empty:
        return ratios_df
    out = pd.DataFrame(index=ratios_df.index)
    for col in ratios_df.columns:
        s = ratios_df[col].dropna()
        if s.empty:
            continue
        if base_date is not None and base_date in s.index:
            base_val = s.loc[base_date]
        else:
            base_val = s.iloc[0]
        if base_val == 0:
            continue
        # Assign rebased values only on s.index to avoid index alignment filling gaps with NaN then ffill
        rebased = (s / base_val) * 100
        out[col] = rebased
    out = out.dropna(how="all")
    return out
