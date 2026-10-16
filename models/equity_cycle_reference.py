"""
Equity bear-market reference (descriptive, not predictive).

Unlike Bitcoin's 4-year halving cycle, S&P 500 / NASDAQ bear markets have no fixed-length
structural driver -- past drawdowns range from ~1 month (2020) to ~30 months (2000-02), so
fitting a "loss shrinks linearly by cycle number" regression the way the BTC module does
would just be curve-fitting noise. Instead this module algorithmically detects historical
peak-to-trough drawdowns past a threshold from real price history, for use as a descriptive
reference table/band alongside the current drawdown -- no projected bottom, no forecast.
"""
from __future__ import annotations

import pandas as pd


def detect_bear_markets(price: pd.Series, threshold: float = 0.20) -> pd.DataFrame:
    """
    Peak-to-trough drawdowns >= threshold (e.g. 0.20 = 20%+ decline = "bear market").
    A bear market runs from the prior all-time high (peak) to its lowest point (trough);
    it "ends" when price makes a new all-time high (recovery). The most recent event may
    still be in progress (no recovery yet).

    Returns a DataFrame with one row per event:
    peak_date, peak_price, trough_date, trough_price, loss_pct (negative),
    decline_days, recovery_date (NaT if in_progress), recovery_days (None if in_progress),
    in_progress (bool).
    """
    price = price.dropna() if price is not None else pd.Series(dtype=float)
    if price.empty:
        return pd.DataFrame()

    peak_price = float(price.iloc[0])
    peak_date = price.index[0]
    trough_price = peak_price
    trough_date = peak_date
    in_drawdown = False
    events: list[dict] = []

    for dt, p in price.items():
        p = float(p)
        if p >= peak_price:
            if in_drawdown:
                events.append({
                    "peak_date": peak_date,
                    "peak_price": peak_price,
                    "trough_date": trough_date,
                    "trough_price": trough_price,
                    "loss_pct": (trough_price / peak_price - 1) * 100,
                    "decline_days": (trough_date - peak_date).days,
                    "recovery_date": dt,
                    "recovery_days": (dt - trough_date).days,
                    "in_progress": False,
                })
                in_drawdown = False
            peak_price = p
            peak_date = dt
            trough_price = p
            trough_date = dt
        else:
            if p < trough_price:
                trough_price = p
                trough_date = dt
            if (p / peak_price - 1) <= -threshold:
                in_drawdown = True

    if in_drawdown:
        events.append({
            "peak_date": peak_date,
            "peak_price": peak_price,
            "trough_date": trough_date,
            "trough_price": trough_price,
            "loss_pct": (trough_price / peak_price - 1) * 100,
            "decline_days": (trough_date - peak_date).days,
            "recovery_date": pd.NaT,
            "recovery_days": None,
            "in_progress": True,
        })

    return pd.DataFrame(events)


def current_drawdown_snapshot(price: pd.Series) -> dict:
    """Live price vs. all-time high: current drawdown %, ATH price/date, and whether it
    already qualifies as a bear market (>=20% off ATH)."""
    price = price.dropna() if price is not None else pd.Series(dtype=float)
    if price.empty:
        return {}
    ath_price = float(price.max())
    ath_date = price.idxmax()
    last_price = float(price.iloc[-1])
    drawdown_pct = (last_price / ath_price - 1) * 100
    return {
        "last_price": last_price,
        "ath_price": ath_price,
        "ath_date": ath_date,
        "drawdown_pct": drawdown_pct,
        "is_bear_market": drawdown_pct <= -20.0,
    }
