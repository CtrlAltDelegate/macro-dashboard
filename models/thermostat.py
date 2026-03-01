"""
Chart 3 — Risk Thermostat (0–100 regime scale).

Translates macro risk into allocation zones:
0–25 Risk-on | 25–50 Neutral | 50–70 De-risk high beta | 70–85 Defensive | 85–100 Capital preservation
"""
from __future__ import annotations

import pandas as pd
import numpy as np


def compute_risk_thermostat(
    macro_risk_composite: pd.Series,
    window: int = 252,
) -> pd.Series:
    """
    Map standardized macro risk composite to 0–100 scale using rolling percentile.
    Higher composite = higher thermostat = more defensive zone.
    """
    if macro_risk_composite.empty or len(macro_risk_composite) < 2:
        return pd.Series(dtype=float)

    roll = macro_risk_composite.rolling(window, min_periods=min(60, window))
    pct = roll.apply(lambda x: (x.iloc[-1] > x).mean() * 100 if len(x) > 0 else np.nan, raw=False)
    return pct.dropna().clip(0, 100)
