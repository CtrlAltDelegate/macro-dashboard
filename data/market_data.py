"""
Market/ETF/crypto data (Rotation Ladder, BTC fallback). Uses Yahoo Finance.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

import config

log = logging.getLogger(__name__)


def _download(tickers: list[str], start: str | None) -> pd.DataFrame:
    """Daily, adjusted Yahoo download from `start` (YYYY-MM-DD; None = full history).

    Uses start= rather than period= because Yahoo only accepts fixed periods (1y, 2y, 5y, 10y, max),
    so lookbacks like 3y would silently return nothing. Retries once on rate limiting.
    """
    kwargs = dict(interval="1d", group_by="ticker", auto_adjust=True, progress=False, threads=False)
    if start:
        kwargs["start"] = start
    else:
        kwargs["period"] = "max"
    for attempt in range(2):
        try:
            return yf.download(tickers, **kwargs)
        except Exception as e:
            rate_limited = "ratelimit" in type(e).__name__.lower() or "rate" in str(e).lower() or "429" in str(e)
            if attempt == 0 and rate_limited:
                time.sleep(3)
                continue
            log.warning("Yahoo download failed for %s: %s", tickers, e)
            return pd.DataFrame()
    return pd.DataFrame()


def _extract_closes(data: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Return a DataFrame of Close prices with one column per ticker (only tickers that came back)."""
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        # group_by="ticker" → (Ticker, Price); older yfinance versions may use (Price, Ticker)
        for level in (1, 0):
            if "Close" in data.columns.get_level_values(level):
                close_df = data.xs("Close", axis=1, level=level)
                break
        else:
            return pd.DataFrame()
    elif "Close" in data.columns:
        close_df = data[["Close"]].rename(columns={"Close": tickers[0]})
    else:
        return pd.DataFrame()
    if isinstance(close_df, pd.Series):
        close_df = close_df.to_frame(tickers[0])
    available = [t for t in tickers if t in close_df.columns]
    return close_df[available].ffill().dropna(how="all") if available else pd.DataFrame()


def fetch_bitcoin_yfinance(start: str | None = None) -> pd.Series:
    """Fetch BTC-USD close from Yahoo Finance (fallback when FRED CBBTCUSD unavailable)."""
    closes = _extract_closes(_download(["BTC-USD"], start), ["BTC-USD"])
    if closes.empty:
        return pd.Series(dtype=float)
    return closes["BTC-USD"].dropna()


def fetch_bitcoin_data(observation_start: str | None = None) -> pd.Series:
    """FRED-first Bitcoin price. Tries CBBTCUSD, then falls back to yfinance BTC-USD."""
    from .fred_data import fetch_bitcoin_fred

    btc = fetch_bitcoin_fred(observation_start=observation_start)
    if btc is not None and len(btc) >= 10:
        return btc
    return fetch_bitcoin_yfinance(start=observation_start)


# Display labels for ladder pairs (falls back to "A/B")
_LADDER_LABELS = {
    ("ETH-USD", "BTC-USD"): "ETH/BTC",
    ("BTC-USD", "SPY"): "BTC/SPY",
    ("SPY", "GLD"): "SPY/GLD",
    ("GLD", "TLT"): "GLD/TLT",
}


def fetch_rotation_ladder_data(start: str | None = None) -> pd.DataFrame:
    """Fetch close prices for rotation ladder pairs (ETH/BTC, BTC/SPY, SPY/GLD, GLD/TLT). Returns ratio columns."""
    pairs = config.ROTATION_LADDER_PAIRS
    tickers = sorted({t for pair in pairs for t in pair})
    closes = _extract_closes(_download(tickers, start), tickers)
    if len(closes.columns) < 2:
        return pd.DataFrame()
    ratios = pd.DataFrame(index=closes.index)
    for a, b in pairs:
        if a in closes.columns and b in closes.columns:
            ratios[_LADDER_LABELS.get((a, b), f"{a}/{b}")] = closes[a] / closes[b]
    return ratios.ffill().dropna(how="all")
