"""
BTC metrics for Markets tab: weekly WMAs, ROC, distances, log-regression Balanced/Terminal price.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _wma(series: pd.Series, n: int) -> pd.Series:
    """Weighted moving average: weights 1..n, WMA = sum(price * weight) / sum(weights)."""
    if series.empty or n < 1 or len(series) < n:
        return pd.Series(dtype=float)
    weights = np.arange(1, n + 1, dtype=float)
    out = series.rolling(window=n).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    return out


def weekly_close(btc_series: pd.Series) -> pd.Series:
    """Resample to weekly (week ending Friday)."""
    if btc_series is None or btc_series.empty:
        return pd.Series(dtype=float)
    s = btc_series.ffill().dropna()
    if s.empty:
        return pd.Series(dtype=float)
    weekly = s.resample("W-FRI").last().dropna()
    return weekly


def compute_btc_snapshot(btc_series: pd.Series, terminal_k: float = 2.0) -> dict:
    """
    Compute BTC snapshot: price, 50/100/200/300 WMA, ROC 1W/4W/12W/52W,
    dist 200WMA/300WMA %, Balanced price (proxy), Terminal price (proxy).
    Returns dict with keys; missing data → None or empty.
    """
    out = {
        "price": None,
        "wma50": None, "wma100": None, "wma200": None, "wma300": None,
        "roc1w": None, "roc4w": None, "roc12w": None, "roc52w": None,
        "dist_200wma_pct": None, "dist_300wma_pct": None,
        "balanced_price": None, "terminal_price": None,
    }
    if btc_series is None or btc_series.empty or len(btc_series) < 2:
        return out
    weekly = weekly_close(btc_series)
    if weekly.empty or len(weekly) < 2:
        out["price"] = float(btc_series.iloc[-1])
        return out
    out["price"] = float(weekly.iloc[-1])
    for n, key in [(50, "wma50"), (100, "wma100"), (200, "wma200"), (300, "wma300")]:
        w = _wma(weekly, n)
        if not w.empty and pd.notna(w.iloc[-1]):
            out[key] = float(w.iloc[-1])
    # ROC
    for period, key in [(1, "roc1w"), (4, "roc4w"), (12, "roc12w"), (52, "roc52w")]:
        if len(weekly) > period:
            pct = (weekly.iloc[-1] / weekly.iloc[-1 - period] - 1) * 100
            out[key] = float(pct)
    # Distance from 200/300 WMA
    wma200 = out.get("wma200")
    wma300 = out.get("wma300")
    if wma200 is not None and wma200 != 0:
        out["dist_200wma_pct"] = (out["price"] / wma200 - 1) * 100
    if wma300 is not None and wma300 != 0:
        out["dist_300wma_pct"] = (out["price"] / wma300 - 1) * 100
    # Balanced / Terminal from log regression (use full weekly history available here)
    balanced, terminal = _balanced_terminal_proxy(weekly, k=terminal_k)
    if balanced is not None:
        out["balanced_price"] = float(balanced)
    if terminal is not None:
        out["terminal_price"] = float(terminal)
    return out


def _balanced_terminal_proxy(weekly: pd.Series, k: float = 2.0) -> tuple[float | None, float | None]:
    """
    Log regression: log(price) ~ a + b*log(t). Midline = exp(a + b*log(t)).
    Balanced (proxy) = midline at last date.
    Terminal (proxy) = lower band = midline * exp(-k * stdev_residual) at last date.
    """
    if weekly is None or len(weekly) < 30:
        return None, None
    t0 = weekly.index.min()
    t_days = (weekly.index - t0).days.values.astype(float)
    t_days[t_days < 1] = 1
    log_t = np.log(t_days)
    log_p = np.log(weekly.values.astype(float))
    log_p[log_p != log_p] = 0
    # regress log_p on log_t
    X = np.column_stack([np.ones_like(log_t), log_t])
    try:
        beta, _, _, _ = np.linalg.lstsq(X, log_p, rcond=None)
        a, b = beta[0], beta[1]
        midline_log = a + b * log_t
        residuals = log_p - midline_log
        stdev_residual = np.nanstd(residuals)
        if np.isnan(stdev_residual) or stdev_residual <= 0:
            stdev_residual = 0.3
        balanced = np.exp(midline_log[-1])
        terminal = np.exp(midline_log[-1] - k * stdev_residual)
        return float(balanced), float(terminal)
    except Exception:
        return None, None


def btc_rainbow_regression(
    btc_series: pd.Series,
    t0_date: str | None = "2010-07-17",
    k_bands: list[float] | None = None,
) -> tuple[pd.Series, pd.Series, dict[float, dict[str, pd.Series]], float, float, float] | None:
    """
    Full-history log regression for Rainbow chart.
    log(price) ~ a + b*log(t), t = days since t0.
    Returns (price, midline, bands_dict, a, b, stdev_residual).
    bands_dict[k] = {"lower": series, "upper": series}.
    """
    if btc_series is None or btc_series.empty or len(btc_series) < 30:
        return None
    if k_bands is None:
        k_bands = [0.5, 1.0, 1.5, 2.0]
    price = btc_series.ffill().dropna()
    if price.empty or len(price) < 30:
        return None
    t0 = pd.Timestamp(t0_date) if t0_date else price.index.min()
    if price.index.min() < t0:
        t0 = price.index.min()
    t_days = (price.index - t0).days.values.astype(float)
    t_days[t_days < 1] = 1
    log_t = np.log(t_days)
    log_p = np.log(price.values.astype(float))
    X = np.column_stack([np.ones_like(log_t), log_t])
    try:
        beta, _, _, _ = np.linalg.lstsq(X, log_p, rcond=None)
        a, b = float(beta[0]), float(beta[1])
        midline_log = a + b * log_t
        residuals = log_p - midline_log
        stdev_residual = float(np.nanstd(residuals))
        if np.isnan(stdev_residual) or stdev_residual <= 0:
            stdev_residual = 0.3
        midline = pd.Series(np.exp(midline_log), index=price.index)
        bands = {}
        for k in k_bands:
            bands[k] = {
                "lower": pd.Series(np.exp(midline_log - k * stdev_residual), index=price.index),
                "upper": pd.Series(np.exp(midline_log + k * stdev_residual), index=price.index),
            }
        return (price, midline, bands, a, b, stdev_residual)
    except Exception:
        return None
