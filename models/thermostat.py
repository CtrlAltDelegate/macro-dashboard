"""
Chart 3 — Risk Thermostat (0–100 regime scale).

Rolling percentile of the macro risk composite, bucketed into RISK_ZONES. The zones are the single
source of truth for labels, chart lines and band shading across all tabs.
"""
from __future__ import annotations

import pandas as pd

# (low, high, label) on the 0–100 scale
RISK_ZONES = [
    (0, 20, "Very Low Risk"),
    (20, 40, "Low Risk"),
    (40, 60, "Moderate Risk"),
    (60, 75, "High Risk"),
    (75, 90, "Very High Risk"),
    (90, 100, "Extreme Risk"),
]


def risk_zone_index(value: float) -> int:
    """Index into RISK_ZONES for a 0–100 score (100 maps to the top zone)."""
    for i, (lo, hi, _label) in enumerate(RISK_ZONES):
        if lo <= value < hi:
            return i
    return len(RISK_ZONES) - 1 if value >= 100 else 0


def risk_zone(value: float) -> str:
    """Zone label (e.g. 'Moderate Risk') for a 0–100 score."""
    return RISK_ZONES[risk_zone_index(value)][2]


def stable_zone_index(scores: pd.Series, min_obs: int = 10) -> pd.Series:
    """Zone index per date, ignoring excursions into another zone shorter than `min_obs` observations.

    A real regime change is backdated to where its run started (no lag); brief blips across a
    boundary keep the previous zone, so band shading doesn't flicker.
    """
    raw = scores.apply(risk_zone_index).to_numpy()
    if len(raw) == 0:
        return pd.Series(dtype=int, index=scores.index)
    out = raw.copy()
    current = raw[0]
    run_zone, run_start = None, 0
    for i, z in enumerate(raw):
        if z == current:
            run_zone = None
        elif z != run_zone:
            run_zone, run_start = z, i
        if run_zone is not None and i - run_start + 1 >= min_obs:
            current = run_zone
            out[run_start:i + 1] = current
            run_zone = None
        out[i] = current
    return pd.Series(out, index=scores.index)


def compute_risk_thermostat(
    macro_risk_composite: pd.Series,
    window: pd.Timedelta = pd.Timedelta(days=365),
) -> pd.Series:
    """
    Map standardized macro risk composite to 0–100 scale using a rolling (calendar-window) percentile.
    Higher composite = higher thermostat = more defensive zone.
    """
    if macro_risk_composite.empty or len(macro_risk_composite) < 2:
        return pd.Series(dtype=float)

    roll = macro_risk_composite.rolling(window, min_periods=60)
    # Share of the window strictly below the latest value: (min-rank - 1) / count. Vectorized
    # equivalent of apply(lambda x: (x.iloc[-1] > x).mean()), which was slow on daily data.
    pct = (roll.rank(method="min") - 1) / roll.count() * 100
    return pct.where(roll.count() >= 60).dropna().clip(0, 100)
