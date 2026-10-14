"""
FRED data fetching. Requires FRED_API_KEY in environment (free key from FRED).
"""
from __future__ import annotations

import logging

import pandas as pd
from fredapi import Fred

import config

log = logging.getLogger(__name__)


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


def _fetch_or_empty(client: Fred, series_id: str, observation_start: str | None) -> pd.Series:
    """Fetch one series (forward-filled, NaNs dropped). Logs and returns an empty Series on failure."""
    try:
        return client.get_series(series_id, observation_start=observation_start).ffill().dropna()
    except Exception as e:
        log.warning("FRED series %s failed: %s", series_id, e)
        return pd.Series(dtype=float)


def _fetch_frame(ids: dict[str, str], observation_start: str | None) -> pd.DataFrame:
    """Fetch {column: series_id} on the union of their dates.

    Not forward-filled, so df[col].dropna() is each series at its native frequency (monthly CPI stays
    monthly) and year-over-year changes line up with real observations. Consumers that combine
    columns forward-fill themselves (e.g. compute_macro_risk_composite, the valuation index).
    """
    client = _get_fred_client()
    out = {name: _fetch_or_empty(client, sid, observation_start) for name, sid in ids.items()}
    return pd.DataFrame(out).dropna(how="all")


def _fetch_single(series_id: str, observation_start: str | None) -> pd.Series:
    if not config.FRED_API_KEY:
        return pd.Series(dtype=float)
    return _fetch_or_empty(_get_fred_client(), series_id, observation_start)


def fetch_valuation_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch all series needed for Chart 1 — Valuation Pressure Index."""
    return _fetch_frame(config.FRED_VALUATION, observation_start)


def fetch_macro_risk_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch all series needed for Chart 2 — Macro Risk Dashboard."""
    return _fetch_frame(config.FRED_MACRO_RISK, observation_start)


def fetch_yield_curve_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch 10Y and 3M Treasury yields for Chart 3 — Yield curve spread (10Y – 3M)."""
    return _fetch_frame(config.FRED_YIELD_CURVE, observation_start)


def fetch_liquidity_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch WALCL (Fed total assets, millions USD) for Chart 4 — Global Liquidity YoY."""
    df = _fetch_frame(config.FRED_LIQUIDITY, observation_start)
    if "WALCL" not in df.columns or df["WALCL"].dropna().empty:
        return pd.DataFrame()
    return df


def fetch_oil_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch WTI spot oil (DCOILWTICO) for Markets tab."""
    s = _fetch_single(config.FRED_OIL, observation_start)
    return pd.DataFrame({"DCOILWTICO": s}) if not s.empty else pd.DataFrame()


def fetch_bitcoin_fred(observation_start: str | None = None) -> pd.Series:
    """Fetch Bitcoin price from FRED (CBBTCUSD). Returns empty Series if unavailable."""
    return _fetch_single(config.FRED_BTC, observation_start)


def fetch_real_yield_data(observation_start: str | None = None) -> pd.Series:
    """Fetch 10-Year TIPS yield (DFII10) for BTC overlay."""
    return _fetch_single(config.FRED_REAL_YIELD, observation_start)


def fetch_recession_periods(observation_start: str | None = None) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """NBER recessions (USREC) as [(start, end)] — end is the last day of the final recession month.
    Note NBER dates are announced with a lag, so a recession in progress may not show yet."""
    s = _fetch_single(config.FRED_RECESSION, observation_start)
    if s.empty:
        return []
    flag = s.astype(bool)
    run_id = (flag != flag.shift()).cumsum()
    periods = []
    for _, months in s[flag].groupby(run_id[flag]):
        periods.append((months.index[0], months.index[-1] + pd.offsets.MonthEnd(0)))
    return periods


def fetch_fiscal_data(observation_start: str | None = None) -> pd.DataFrame:
    """Fetch fiscal series for Fiscal tab: Deficit % GDP, Debt % GDP, Net Interest, GDP.
    Returns DataFrame with columns: DEFICIT_PCT_GDP (positive = deficit), DEBT_PCT_GDP,
    NET_INTEREST, GDP, INTEREST_PCT_GDP (computed).
    """
    if not config.FRED_API_KEY:
        return pd.DataFrame()
    df = _fetch_frame(config.FRED_FISCAL, observation_start)
    if "DEFICIT_PCT_GDP" not in df.columns or df["DEFICIT_PCT_GDP"].dropna().empty:
        return pd.DataFrame()
    # Deficit as positive % of GDP (FRED series: surplus positive, deficit negative)
    df["DEFICIT_PCT_GDP"] = -df["DEFICIT_PCT_GDP"]
    # Interest as % of GDP (quarterly)
    if df["NET_INTEREST"].notna().sum() >= 2 and df["GDP"].notna().sum() >= 2:
        df["INTEREST_PCT_GDP"] = (df["NET_INTEREST"] / df["GDP"]) * 100
    return df


def fetch_model_input_series(observation_start: str | None = None) -> dict[str, pd.Series]:
    """Fetch extra series for Model Inputs: 2Y yield, Core CPI, Initial Claims.
    Returns dict with keys DGS2, CPILFESL, ICSA (each value a Series or empty)."""
    return {
        "DGS2": _fetch_single(config.FRED_DGS2, observation_start),
        "CPILFESL": _fetch_single(config.FRED_CORE_CPI, observation_start),
        "ICSA": _fetch_single(config.FRED_INITIAL_CLAIMS, observation_start),
    }
