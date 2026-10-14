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


# ---------------------------------------------------------------------------
# Secrets: environment / .env first, then Streamlit secrets (root key or [section])
# ---------------------------------------------------------------------------
def get_secret(name: str) -> str:
    """Return a secret from the environment, else st.secrets (root-level or any section). '' if unset."""
    val = os.getenv(name, "")
    if val:
        return val
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name] or "")
        for section in st.secrets.values():
            if hasattr(section, "get") and section.get(name):
                return str(section.get(name))
    except Exception:
        pass  # no Streamlit, or no secrets.toml
    return ""


# ---------------------------------------------------------------------------
# FRED API (free key: https://fred.stlouisfed.org/docs/api/api_key.html)
# ---------------------------------------------------------------------------
FRED_API_KEY = get_secret("FRED_API_KEY")

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

# Chart 3 — Yield curve (10Y – 3M spread, plus 10Y – 2Y)
FRED_YIELD_CURVE = {
    "DGS10": "DGS10",     # 10-Year Treasury Constant Maturity Rate
    "DGS3MO": "DGS3MO",   # 3-Month Treasury Constant Maturity Rate
    "T10Y2Y": "T10Y2Y",   # 10-Year minus 2-Year Treasury spread (percentage points)
}

# Chart 4 — Global Liquidity (Fed balance sheet YoY) + Net liquidity
FRED_LIQUIDITY = {
    "WALCL": "WALCL",     # Fed total assets (balance sheet), weekly, millions USD
    "TGA": "WTREGEN",     # Treasury General Account, weekly, millions USD
    "RRP": "RRPONTSYD",   # Overnight reverse repo, daily, billions USD
}

# NBER recession indicator (monthly, 1 = recession) for chart shading
FRED_RECESSION = "USREC"

# Markets tab — Oil (FRED), Bitcoin (FRED then yfinance fallback)
FRED_OIL = "DCOILWTICO"   # WTI spot oil
FRED_BTC = "CBBTCUSD"     # Coinbase BTC/USD (FRED)
FRED_CPI = "CPIAUCSL"     # CPI (for oil overlay; also in FRED_MACRO_RISK as INFLATION)
FRED_REAL_YIELD = "DFII10"  # 10-Year TIPS yield (real yields for BTC overlay)

# Tab 3 — Rotation ladder (z-score normalized ratios). Order: risk-on → defensive.
ROTATION_LADDER_PAIRS = [
    ("ETH-USD", "BTC-USD"),  # ALTS/BTC
    ("BTC-USD", "SPY"),      # BTC/SPX
    ("SPY", "GLD"),          # SPX/Gold
    ("GLD", "TLT"),          # Gold/Bonds
]

# Fiscal tab — deficit, debt, interest burden
# FYFSGDA188S = Federal Surplus or Deficit [-] as % of GDP (annual; deficit negative → use -series for Deficit % GDP)
# FYGFDPUN = Federal Debt as Percent of GDP (annual)
# B091RC1Q027SBEA = Federal net interest (quarterly, billions); GDP = quarterly GDP for interest % GDP
FRED_FISCAL = {
    "DEFICIT_PCT_GDP": "FYFSGDA188S",   # Surplus/Deficit as % GDP (deficit = negative)
    "DEBT_PCT_GDP": "FYGFDPUN",         # Debt as % of GDP
    "NET_INTEREST": "B091RC1Q027SBEA",  # Net interest outlays (quarterly, billions)
    "GDP": "GDP",                       # Quarterly GDP (billions, SAAR) for interest burden
}

# Model inputs (extra series for Macro tab: 2Y yield, Core CPI, Initial Claims)
FRED_DGS2 = "DGS2"           # 2-Year Treasury
FRED_CORE_CPI = "CPILFESL"   # Core CPI (less food and energy)
FRED_INITIAL_CLAIMS = "ICSA" # Initial Jobless Claims (weekly)

# AI interpretation (optional): OpenAI for lightweight summary
OPENAI_API_KEY = get_secret("OPENAI_API_KEY")
