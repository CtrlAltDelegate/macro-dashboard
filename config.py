"""
Configuration: FRED series IDs and market tickers for the Macro Dashboard.
All data sources are free (FRED + Yahoo Finance).
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_DIR = PROJECT_ROOT / "cache"
EXPORTS_DIR = PROJECT_ROOT / "exports"
CACHE_DIR.mkdir(exist_ok=True)
EXPORTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Lookback options (sidebar + refresh script)
# ---------------------------------------------------------------------------
LOOKBACK_OPTIONS = ["1y", "3y", "5y", "10y", "Max"]


def lookback_to_observation_start(lookback: str) -> str | None:
    """Map lookback label to FRED observation_start (YYYY-MM-DD). None = Max (all data)."""
    if lookback == "Max":
        return None
    today = datetime.now().date()
    if lookback == "1y":
        start = today - timedelta(days=365)
    elif lookback == "3y":
        start = today - timedelta(days=3 * 365)
    elif lookback == "5y":
        start = today - timedelta(days=5 * 365)
    elif lookback == "10y":
        start = today - timedelta(days=10 * 365)
    else:
        return None
    return start.isoformat()


def lookback_to_rotation_period(lookback: str) -> str:
    """Map lookback to Yahoo Finance period for rotation data (e.g. 1y, 2y, max)."""
    if lookback == "Max":
        return "10y"  # yfinance typical max for daily
    return lookback

# ---------------------------------------------------------------------------
# FRED API (free key: https://fred.stlouisfed.org/docs/api/api_key.html)
# ---------------------------------------------------------------------------
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# Chart 1 — Valuation Pressure Index
FRED_VALUATION = {
    "SP500": "SP500",           # S&P 500
    "UNRATE": "UNRATE",         # Unemployment rate
    "INFLATION": "CPIAUCSL",   # CPI (inflation proxy)
    "FEDFUNDS": "FEDFUNDS",    # Federal funds rate
    "M2": "M2SL",              # M2 money supply
}

# Chart 2 — Macro Risk Dashboard pillars
FRED_MACRO_RISK = {
    "GDP": "GDPC1",                    # Real GDP
    "UNEMPLOYMENT": "UNRATE",          # Unemployment rate
    "INFLATION": "CPIAUCSL",           # CPI
    "CREDIT_TIGHTENING": "NFCI",       # Chicago Fed NFCI
    "LIQUIDITY": "WALCL",              # Fed balance sheet (total assets)
    "CREDIT_STRESS": "BAMLH0A0HYM2",   # ICE BofA US HY OAS
}

# Chart 4 — Rotation (Yahoo Finance tickers; FRED has limited ETF/crypto)
ROTATION_PAIRS = [
    ("ALT", "BTC-USD"),   # Alts vs Bitcoin (use ETH-USD or a basket as ALT proxy)
    ("BTC-USD", "SPY"),   # Bitcoin vs S&P 500
    ("IWM", "SPY"),       # Small cap vs large cap
    ("HYG", "IEF"),       # High yield vs 7–10Y Treasuries
    ("XLU", "SPY"),       # Utilities (defensive) vs S&P 500
]
# If no ALT ticker, we use ETH-USD as first “risk” asset
ROTATION_ALT_TICKER = "ETH-USD"
