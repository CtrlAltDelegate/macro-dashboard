"""
Market/ETF/crypto data for Chart 4 — Risk Cascade (rotation). Uses Yahoo Finance.
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

import config


def fetch_rotation_data(
    period: str = "2y",
    interval: str = "1d",
) -> pd.DataFrame:
    """
    Fetch close prices for rotation pairs. Returns DataFrame with columns
    like ALT_BTC, BTC_SPY, IWM_SPY, HYG_IEF, XLU_SPY (ratio names).
    """
    # Build list of unique tickers; use ETH as ALT if ALT not a real ticker
    pairs = list(config.ROTATION_PAIRS)
    tickers = set()
    for a, b in pairs:
        tickers.add(a if a != "ALT" else config.ROTATION_ALT_TICKER)
        tickers.add(b)
    tickers = sorted(tickers)

    data = yf.download(
        tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    if data.empty:
        return pd.DataFrame()

    # yfinance: with multiple tickers, columns can be MultiIndex (Ticker, OHLCV) or flat
    if isinstance(data.columns, pd.MultiIndex):
        close_df = data["Close"].copy()
        close_df.columns = close_df.columns.get_level_values(0)
    else:
        close_df = data["Close"] if "Close" in data.columns else data
    if close_df.empty:
        return pd.DataFrame()
    if isinstance(close_df, pd.Series):
        close_df = close_df.to_frame(tickers[0] if tickers else "Close")
    # Keep only columns that match our tickers (yfinance may use different names)
    available = [c for c in tickers if c in close_df.columns]
    closes = close_df[available].ffill().dropna(how="all") if available else pd.DataFrame()

    # Build ratio series with consistent naming for display
    name_map = {
        ("ETH-USD", "BTC-USD"): "ALT/BTC",
        ("BTC-USD", "SPY"): "BTC/SPY",
        ("IWM", "SPY"): "IWM/SPY",
        ("HYG", "IEF"): "HYG/IEF",
        ("XLU", "SPY"): "XLU/SPY",
    }
    # Support ALT as first element
    pair_to_col = []
    for a, b in pairs:
        t_a = config.ROTATION_ALT_TICKER if a == "ALT" else a
        t_b = b
        key = (t_a, t_b)
        label = name_map.get(key, f"{t_a}/{t_b}")
        pair_to_col.append((t_a, t_b, label))

    ratios = pd.DataFrame(index=closes.index)
    for t_a, t_b, label in pair_to_col:
        if t_a in closes.columns and t_b in closes.columns:
            ratios[label] = closes[t_a] / closes[t_b]
    ratios = ratios.ffill().dropna(how="all")
    return ratios
