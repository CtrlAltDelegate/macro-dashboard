"""
Bitcoin Cycle Regression Model.

Fits the historical pattern of BTC bull-market gains (bottom -> top) and bear-market
losses (top -> next bottom) across completed 4-year halving cycles, then projects the
current cycle's drawdown/rebound using those fits. Small sample size (n=3 completed
cycles) -> point estimates are scenario anchors, not forecasts; always pair with a band.

Cycle numbering and structural rationale (halving-driven ~4yr supply shock) per
btc-cycle-regression-model.md (Jul 2026 spec).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BtcCycle:
    cycle: int
    bottom_price: float
    bottom_date: str
    top_price: float
    top_date: str
    next_bottom_price: float | None = None
    next_bottom_date: str | None = None


# Seed dataset. Extend with one row per completed cycle; cycle 4 top is confirmed,
# next bottom is unresolved (in progress) as of this module's creation (Jul 2026).
BTC_CYCLES: list[BtcCycle] = [
    BtcCycle(1, 2, "2011-01-01", 1150, "2013-11-01", 150, "2015-01-01"),
    BtcCycle(2, 150, "2015-01-01", 19700, "2017-12-01", 3200, "2018-12-01"),
    BtcCycle(3, 3200, "2018-12-01", 69000, "2021-11-01", 15500, "2022-11-01"),
    BtcCycle(4, 15500, "2022-11-01", 126296, "2025-10-06", None, None),
]

# Cycles with a confirmed next-bottom are used to fit the regressions (currently 1-3).
_FIT_CYCLES: list[BtcCycle] = [c for c in BTC_CYCLES if c.next_bottom_price is not None]


def _loss_pct(c: BtcCycle) -> float:
    """Top -> next bottom, as a negative percent (e.g. -87.0)."""
    return (c.next_bottom_price / c.top_price - 1) * 100


def _multiple(c: BtcCycle) -> float:
    """Bottom -> top multiple (e.g. 8.15)."""
    return c.top_price / c.bottom_price


def bear_loss_model(cycle_number: float) -> dict:
    """
    Linear regression: Loss%(cycle) = a + b*cycle, fit on completed cycles.
    Returns point estimate + a naive +/-1 residual-stdev band. Empty dict if <2 fit points.
    """
    xs = np.array([c.cycle for c in _FIT_CYCLES], dtype=float)
    ys = np.array([_loss_pct(c) for c in _FIT_CYCLES], dtype=float)
    if len(xs) < 2:
        return {}
    b, a = np.polyfit(xs, ys, 1)
    resid = ys - (a + b * xs)
    sigma = float(np.std(resid))
    point = float(a + b * cycle_number)
    return {
        "loss_pct": point,
        "loss_pct_low": point - sigma,   # more negative = deeper projected loss
        "loss_pct_high": point + sigma,  # less negative = shallower projected loss
        "slope": float(b),
        "intercept": float(a),
        "sigma": sigma,
        "n": len(xs),
    }


def bull_gain_model(cycle_number: float) -> dict:
    """
    Log-linear regression: log10(Multiple(cycle)) = a - b*cycle, fit on completed cycles
    (bottom->top gain compounds, so fit in log space rather than raw %).
    Returns point estimate + a naive +/-1 residual-stdev band. Empty dict if <2 fit points.
    """
    xs = np.array([c.cycle for c in _FIT_CYCLES], dtype=float)
    ys = np.log10(np.array([_multiple(c) for c in _FIT_CYCLES], dtype=float))
    if len(xs) < 2:
        return {}
    b, a = np.polyfit(xs, ys, 1)
    resid = ys - (a + b * xs)
    sigma = float(np.std(resid))
    log_point = a + b * cycle_number
    return {
        "multiple": float(10 ** log_point),
        "multiple_low": float(10 ** (log_point - sigma)),
        "multiple_high": float(10 ** (log_point + sigma)),
        "slope": float(b),
        "intercept": float(a),
        "sigma": sigma,
        "n": len(xs),
    }


def cycle_history_table() -> pd.DataFrame:
    """Actual per-cycle loss% and multiple for completed cycles (for charting vs. the fitted line)."""
    rows = []
    for c in _FIT_CYCLES:
        rows.append({
            "cycle": c.cycle,
            "loss_pct": _loss_pct(c),
            "multiple": _multiple(c),
            "log10_multiple": np.log10(_multiple(c)),
        })
    return pd.DataFrame(rows)


def compute_cycle_snapshot(btc_price: float | None, as_of: pd.Timestamp | None = None) -> dict:
    """
    Current (in-progress) cycle tracker: live price vs. projected bottom band, drawdown
    from cycle top, days elapsed vs. historical bear-market durations, and the Model 2
    bull-gain divergence flag (actual multiple vs. model-projected multiple).
    """
    current = BTC_CYCLES[-1]
    out: dict = {
        "cycle_number": current.cycle,
        "top_price": current.top_price,
        "top_date": current.top_date,
    }
    if btc_price is not None and current.top_price:
        out["drawdown_from_top_pct"] = (btc_price / current.top_price - 1) * 100

    bear = bear_loss_model(current.cycle)
    if bear:
        top = current.top_price
        out["bear_model"] = bear
        out["projected_bottom"] = top * (1 + bear["loss_pct"] / 100)
        out["projected_bottom_low"] = top * (1 + bear["loss_pct_low"] / 100)
        out["projected_bottom_high"] = top * (1 + bear["loss_pct_high"] / 100)

    durations_days = [
        (pd.Timestamp(c.next_bottom_date) - pd.Timestamp(c.top_date)).days for c in _FIT_CYCLES
    ]
    if durations_days:
        out["historical_bear_duration_min_days"] = min(durations_days)
        out["historical_bear_duration_max_days"] = max(durations_days)

    if as_of is None:
        as_of = pd.Timestamp.now()
    out["days_since_top"] = (as_of - pd.Timestamp(current.top_date)).days

    prev = BTC_CYCLES[-2] if len(BTC_CYCLES) >= 2 else None
    if prev is not None and prev.next_bottom_price:
        actual_multiple = current.top_price / prev.next_bottom_price
        bull = bull_gain_model(current.cycle)
        if bull:
            out["bull_model"] = bull
            out["bull_actual_multiple"] = actual_multiple
            out["bull_divergence_pct"] = (actual_multiple / bull["multiple"] - 1) * 100

    return out
