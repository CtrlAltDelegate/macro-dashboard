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
