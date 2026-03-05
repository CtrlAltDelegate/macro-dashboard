"""
Market/ETF/crypto data for Chart 4 — Risk Cascade (rotation). Uses Yahoo Finance.
"""
from __future__ import annotations

import time

import pandas as pd
import yfinance as yf

import config

try:
    from yfinance.exceptions import YFRateLimitError
except ImportError:
    YFRateLimitError = type("YFRateLimitError", (Exception,), {})  # no-op if missing


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

    try:
        data = yf.download(
            tickers,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=False,  # gentler on Yahoo; avoids rate limit when possible
        )
    except (YFRateLimitError, Exception) as e:
        # Rate limited: retry once after a short delay
        if isinstance(e, YFRateLimitError) or "rate" in str(e).lower() or "429" in str(e):
            time.sleep(3)
            try:
                data = yf.download(
                    tickers,
                    period=period,
                    interval=interval,
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                )
            except Exception:
                return pd.DataFrame()
        else:
            return pd.DataFrame()

    if data.empty:
        return pd.DataFrame()

    try:
        # yfinance: with group_by="ticker", columns are MultiIndex (Ticker, Metric) — e.g. (SPY, Close)
        # data["Close"] fails because "Close" is in level 1, not level 0. Extract Close via xs.
        if isinstance(data.columns, pd.MultiIndex):
            if data.columns.nlevels >= 2:
                # Level 1 is typically Open/High/Low/Close/Volume
                if "Close" in data.columns.get_level_values(1):
                    close_df = data.xs("Close", axis=1, level=1).copy()
                else:
                    # fallback: level 0 might be Metric in some versions
                    if "Close" in data.columns.get_level_values(0):
                        close_df = data.xs("Close", axis=1, level=0).copy()
                    else:
                        return pd.DataFrame()
            else:
                return pd.DataFrame()
            # Ensure we have a DataFrame with ticker-named columns (xs may return Series for single ticker)
            if isinstance(close_df, pd.Series):
                close_df = close_df.to_frame(close_df.name if close_df.name else tickers[0])
        else:
            if "Close" not in data.columns:
                return pd.DataFrame()
            close_df = data["Close"].copy()
            if isinstance(close_df, pd.Series):
                close_df = close_df.to_frame(tickers[0] if tickers else "Close")
        if close_df.empty:
            return pd.DataFrame()
        # Keep only columns that match our tickers (yfinance may use different names)
        available = [c for c in tickers if c in close_df.columns]
        closes = close_df[available].ffill().dropna(how="all") if available else pd.DataFrame()
        if closes.empty:
            return pd.DataFrame()

        # Build ratio series with consistent naming for display
        name_map = {
            ("ETH-USD", "BTC-USD"): "ALT/BTC",
            ("BTC-USD", "SPY"): "BTC/SPY",
            ("IWM", "SPY"): "IWM/SPY",
            ("HYG", "IEF"): "HYG/IEF",
            ("XLU", "SPY"): "XLU/SPY",
        }
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
        return ratios.ffill().dropna(how="all")
    except (KeyError, TypeError, AttributeError):
        return pd.DataFrame()


def fetch_bitcoin_yfinance(period: str = "5y", interval: str = "1d") -> pd.Series:
    """Fetch BTC-USD close from Yahoo Finance (fallback when FRED CBBTCUSD unavailable)."""
    try:
        data = yf.download(
            "BTC-USD",
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception:
        return pd.Series(dtype=float)
    if data.empty or "Close" not in data.columns:
        return pd.Series(dtype=float)
    s = data["Close"].ffill().dropna()
    return s


def fetch_bitcoin_data(
    observation_start: str | None,
    yfinance_period: str = "5y",
) -> pd.Series:
    """FRED-first Bitcoin price. Tries CBBTCUSD, then falls back to yfinance BTC-USD."""
    from .fred_data import fetch_bitcoin_fred

    btc = fetch_bitcoin_fred(observation_start=observation_start)
    if btc is not None and not btc.empty and len(btc) >= 10:
        return btc
    return fetch_bitcoin_yfinance(period=yfinance_period)


def fetch_rotation_ladder_data(period: str = "5y", interval: str = "1d") -> pd.DataFrame:
    """Fetch close prices for rotation ladder pairs (ETH/BTC, BTC/SPY, SPY/GLD, GLD/TLT). Returns ratio columns."""
    pairs = getattr(config, "ROTATION_LADDER_PAIRS", [
        ("ETH-USD", "BTC-USD"),
        ("BTC-USD", "SPY"),
        ("SPY", "GLD"),
        ("GLD", "TLT"),
    ])
    tickers = sorted(set(a for a, b in pairs) | set(b for a, b in pairs))
    try:
        data = yf.download(
            tickers,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception:
        return pd.DataFrame()
    if data.empty:
        return pd.DataFrame()
    try:
        if isinstance(data.columns, pd.MultiIndex) and "Close" in data.columns.get_level_values(1):
            close_df = data.xs("Close", axis=1, level=1).copy()
        else:
            if "Close" in data.columns:
                close_df = data[["Close"]].copy() if isinstance(data["Close"], pd.Series) else data["Close"].copy()
                if isinstance(close_df, pd.Series):
                    close_df = close_df.to_frame(tickers[0] if tickers else "Close")
            else:
                return pd.DataFrame()
        if isinstance(close_df, pd.Series):
            close_df = close_df.to_frame(close_df.name or tickers[0])
        available = [c for c in tickers if c in close_df.columns]
        if len(available) < 2:
            return pd.DataFrame()
        closes = close_df[available].ffill().dropna(how="all")
        if closes.empty:
            return pd.DataFrame()
        name_map = {
            ("ETH-USD", "BTC-USD"): "ETH/BTC",
            ("BTC-USD", "SPY"): "BTC/SPY",
            ("SPY", "GLD"): "SPY/GLD",
            ("GLD", "TLT"): "GLD/TLT",
        }
        ratios = pd.DataFrame(index=closes.index)
        for (a, b) in pairs:
            if a in closes.columns and b in closes.columns:
                label = name_map.get((a, b), f"{a}/{b}")
                ratios[label] = closes[a] / closes[b]
        return ratios.ffill().dropna(how="all")
    except (KeyError, TypeError, AttributeError):
        return pd.DataFrame()
