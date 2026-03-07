"""
FRED data fetching. Requires FRED_API_KEY in environment (free key from FRED).
"""
from __future__ import annotations

import pandas as pd
from fredapi import Fred

import config


def _get_fred_client() -> Fred:
    if not config.FRED_API_KEY:
        raise ValueError(
            "FRED_API_KEY not set. Get a free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html and set it in .env"
        )
    return Fred(api_key=config.FRED_API_KEY)


def fetch_fred_series(series_id: str, **kwargs) -> pd.Series:
    """Fetch a single FRED series. kwargs passed to fred.get_series (e.g. observation_start)."""
    client = _get_fred_client()
    return client.get_series(series_id, **kwargs)


def fetch_valuation_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch all series needed for Chart 1 — Valuation Pressure Index."""
    client = _get_fred_client()
    ids = config.FRED_VALUATION
    out = {}
    for name, sid in ids.items():
        try:
            s = client.get_series(sid, observation_start=observation_start)
            s = s.ffill().dropna()
            out[name] = s
        except Exception as e:
            out[name] = pd.Series(dtype=float)  # placeholder on error
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df = df.ffill().dropna(how="all")
    return df


def fetch_macro_risk_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch all series needed for Chart 2 — Macro Risk Dashboard."""
    client = _get_fred_client()
    ids = config.FRED_MACRO_RISK
    out = {}
    for name, sid in ids.items():
        try:
            s = client.get_series(sid, observation_start=observation_start)
            s = s.ffill().dropna()
            out[name] = s
        except Exception:
            out[name] = pd.Series(dtype=float)
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df = df.ffill().dropna(how="all")
    return df


def fetch_yield_curve_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch 10Y and 3M Treasury yields for Chart 3 — Yield curve spread (10Y – 3M)."""
    client = _get_fred_client()
    ids = config.FRED_YIELD_CURVE
    out = {}
    for name, sid in ids.items():
        try:
            s = client.get_series(sid, observation_start=observation_start)
            s = s.ffill().dropna()
            out[name] = s
        except Exception:
            out[name] = pd.Series(dtype=float)
    if not out or "DGS10" not in out or "DGS3MO" not in out:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df = df.ffill().dropna(how="all")
    return df


def fetch_liquidity_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch WALCL (Fed total assets) for Chart 4 — Global Liquidity YoY."""
    client = _get_fred_client()
    ids = config.FRED_LIQUIDITY
    out = {}
    for name, sid in ids.items():
        try:
            s = client.get_series(sid, observation_start=observation_start)
            s = s.ffill().dropna()
            out[name] = s
        except Exception:
            out[name] = pd.Series(dtype=float)
    if not out or "WALCL" not in out or out["WALCL"].empty:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df = df.ffill().dropna(how="all")
    return df


def fetch_oil_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch WTI spot oil (DCOILWTICO) for Markets tab."""
    if not config.FRED_API_KEY:
        return pd.DataFrame()
    try:
        s = fetch_fred_series(config.FRED_OIL, observation_start=observation_start)
        s = s.ffill().dropna()
        if s.empty:
            return pd.DataFrame()
        return pd.DataFrame({"DCOILWTICO": s})
    except Exception:
        return pd.DataFrame()


def fetch_bitcoin_fred(observation_start: str | None = None) -> pd.Series:
    """Fetch Bitcoin price from FRED (CBBTCUSD). Returns empty Series if unavailable."""
    if not config.FRED_API_KEY:
        return pd.Series(dtype=float)
    try:
        s = fetch_fred_series(config.FRED_BTC, observation_start=observation_start)
        s = s.ffill().dropna()
        return s
    except Exception:
        return pd.Series(dtype=float)


def fetch_real_yield_data(observation_start: str | None = None) -> pd.Series:
    """Fetch 10-Year TIPS yield (DFII10) for BTC overlay."""
    if not config.FRED_API_KEY:
        return pd.Series(dtype=float)
    try:
        s = fetch_fred_series(config.FRED_REAL_YIELD, observation_start=observation_start)
        s = s.ffill().dropna()
        return s
    except Exception:
        return pd.Series(dtype=float)


def fetch_fiscal_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch fiscal series for Fiscal tab: Deficit % GDP, Debt % GDP, Net Interest, GDP.
    Returns DataFrame with columns: DEFICIT_PCT_GDP (positive = deficit), DEBT_PCT_GDP,
    NET_INTEREST, GDP, INTEREST_PCT_GDP (computed).
    """
    if not config.FRED_API_KEY:
        return pd.DataFrame()
    client = _get_fred_client()
    out = {}
    for name, sid in config.FRED_FISCAL.items():
        try:
            s = client.get_series(sid, observation_start=observation_start)
            s = s.ffill().dropna()
            out[name] = s
        except Exception:
            out[name] = pd.Series(dtype=float)
    if not out or out.get("DEFICIT_PCT_GDP") is None or out["DEFICIT_PCT_GDP"].empty:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df = df.ffill().dropna(how="all")
    # Deficit as positive % of GDP (FRED series: surplus positive, deficit negative)
    if "DEFICIT_PCT_GDP" in df.columns:
        df["DEFICIT_PCT_GDP"] = -df["DEFICIT_PCT_GDP"]
    # Interest as % of GDP (quarterly)
    if "NET_INTEREST" in df.columns and "GDP" in df.columns:
        ni = df["NET_INTEREST"].dropna()
        gdp = df["GDP"].dropna()
        common = ni.index.intersection(gdp.index)
        if len(common) >= 2:
            df["INTEREST_PCT_GDP"] = (df["NET_INTEREST"] / df["GDP"]) * 100
    return df


def fetch_model_input_series(observation_start: str | None = None) -> dict[str, pd.Series]:
    """Fetch extra series for Model Inputs: 2Y yield, Core CPI, Initial Claims.
    Returns dict with keys DGS2, CPILFESL, ICSA (each value a Series or empty)."""
    if not config.FRED_API_KEY:
        return {"DGS2": pd.Series(dtype=float), "CPILFESL": pd.Series(dtype=float), "ICSA": pd.Series(dtype=float)}
    out = {}
    for key, sid in [
        ("DGS2", config.FRED_DGS2),
        ("CPILFESL", config.FRED_CORE_CPI),
        ("ICSA", config.FRED_INITIAL_CLAIMS),
    ]:
        try:
            s = fetch_fred_series(sid, observation_start=observation_start)
            s = s.ffill().dropna()
            out[key] = s
        except Exception:
            out[key] = pd.Series(dtype=float)
    return out
