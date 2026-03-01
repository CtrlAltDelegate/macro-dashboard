"""
Chart 4 — Risk Cascade Curves (rotation engine).

Relative strength ratios to see which asset breaks first:
ALT/BTC, BTC/SPY, IWM/SPY, HYG/IEF, XLU/SPY.
Normalized (e.g. rebased to 100) for comparable curves.
"""
from __future__ import annotations

import pandas as pd


def prepare_rotation_curves(ratios_df: pd.DataFrame, base_date: str | None = None) -> pd.DataFrame:
    """
    Take ratio series and rebase each to 100 at base_date (or first valid date).
    Returns DataFrame with same columns, values as index levels (100 = start).
    """
    if ratios_df.empty:
        return ratios_df
    out = ratios_df.copy()
    for col in out.columns:
        s = out[col].dropna()
        if s.empty:
            continue
        if base_date is not None and base_date in s.index:
            base_val = s.loc[base_date]
        else:
            base_val = s.iloc[0]
        if base_val == 0:
            continue
        out[col] = (s / base_val) * 100
    return out.ffill().dropna(how="all")
