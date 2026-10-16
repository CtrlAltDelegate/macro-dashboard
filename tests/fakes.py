"""Synthetic data shaped like the real FRED / Yahoo responses (frequencies and units), for offline tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

# Data runs through yesterday, like live FRED data, so date-relative features ("since last issue") have data
END = pd.Timestamp.today().normalize() - pd.Timedelta(days=1)


def _recession_flags(n: int) -> np.ndarray:
    months = pd.date_range("2012-01-01", periods=n, freq="MS")
    return ((months >= "2023-03-01") & (months <= "2023-06-01")).astype(float)


# FRED series ID → (frequency, generator(n) → values)
FRED_SERIES = {
    "SP500": ("B", lambda n: np.linspace(3000, 6600, n)),
    "UNRATE": ("MS", lambda n: 4 + 0.3 * np.sin(np.arange(n) / 8)),
    "CPIAUCSL": ("MS", lambda n: 250 * 1.03 ** (np.arange(n) / 12)),  # exactly 3.0% YoY
    "CPILFESL": ("MS", lambda n: 260 * 1.028 ** (np.arange(n) / 12)),  # 2.8% YoY
    "FEDFUNDS": ("MS", lambda n: np.clip(np.linspace(0.1, 5.3, n), 0, None)),
    "M2SL": ("MS", lambda n: np.linspace(15000, 22000, n)),
    "GDPC1": ("QS", lambda n: 18000 * 1.02 ** (np.arange(n) / 4) * (1 + 0.004 * np.sin(np.arange(n)))),
    "NFCI": ("W-FRI", lambda n: 0.3 * np.sin(np.arange(n) / 15) - 0.4),
    "WALCL": ("W-WED", lambda n: np.linspace(7.5e6, 6.6e6, n)),        # millions USD
    "WTREGEN": ("W-WED", lambda n: 700000 + 150000 * np.sin(np.arange(n) / 9)),  # millions USD
    "RRPONTSYD": ("B", lambda n: np.clip(2200 * np.sin(np.arange(n) / 900), 0, None)),  # billions USD
    "BAMLH0A0HYM2": ("B", lambda n: 3.5 + np.cos(np.arange(n) / 120)),
    "BAMLC0A0CM": ("B", lambda n: 1.1 + 0.2 * np.cos(np.arange(n) / 120)),
    "DGS10": ("B", lambda n: np.full(n, 4.1)),
    "DGS3MO": ("B", lambda n: np.linspace(5.4, 3.9, n)),
    "DGS2": ("B", lambda n: np.linspace(4.8, 3.6, n)),
    "T10Y2Y": ("B", lambda n: np.linspace(-0.8, 0.6, n)),
    "T10YIE": ("B", lambda n: np.full(n, 2.3)),
    "ICSA": ("W-SAT", lambda n: 220000 + 10000 * np.sin(np.arange(n) / 10)),
    "SAHMREALTIME": ("MS", lambda n: np.full(n, 0.27)),
    "DTWEXBGS": ("B", lambda n: np.linspace(110, 122, n)),
    "VIXCLS": ("B", lambda n: 16 + 3 * np.sin(np.arange(n) / 30)),
    "DRTSCILM": ("QS", lambda n: 10 * np.sin(np.arange(n) / 3)),             # net % tightening
    "THREEFYTP10": ("B", lambda n: 0.4 + 0.3 * np.sin(np.arange(n) / 250)),
    "PERMIT": ("MS", lambda n: 1400 + 100 * np.sin(np.arange(n) / 6)),        # thousands, SAAR
    "MORTGAGE30US": ("W-THU", lambda n: np.linspace(3.5, 6.4, n)),
    "DCOILWTICO": ("B", lambda n: 70 + 8 * np.sin(np.arange(n) / 60)),
    "DFII10": ("B", lambda n: np.full(n, 1.8)),
    "FYFSGDA188S": ("YS", lambda n: np.linspace(-3, -6.2, n)),
    "FYGFDPUN": ("YS", lambda n: np.linspace(100, 122, n)),
    "B091RC1Q027SBEA": ("QS", lambda n: np.linspace(500, 1100, n)),
    "GDP": ("QS", lambda n: np.linspace(21000, 30000, n)),
    "USREC": ("MS", _recession_flags),  # synthetic recession Mar–Jun 2023
}


def fred_series(series_id: str, observation_start: str | None = None) -> pd.Series:
    freq, gen = FRED_SERIES[series_id]
    idx = pd.date_range("2012-01-01", END, freq=freq)
    s = pd.Series(gen(len(idx)), index=idx, dtype=float)
    return s[s.index >= pd.Timestamp(observation_start)] if observation_start else s


class FakeFred:
    """Stands in for fredapi.Fred. CBBTCUSD is missing, like a FRED outage, to exercise the Yahoo fallback."""

    def get_series(self, series_id, observation_start=None):
        if series_id not in FRED_SERIES:
            raise KeyError(f"no such fake series {series_id}")
        return fred_series(series_id, observation_start)


def btc_prices(start: str | None = None) -> pd.Series:
    idx = pd.date_range("2014-09-17", END, freq="D")
    s = pd.Series(np.exp(np.linspace(6, 11.3, len(idx))) * (1 + 0.2 * np.sin(np.arange(len(idx)) / 200)), index=idx)
    return s[s.index >= pd.Timestamp(start)] if start else s


def market_ratios(start: str | None = None) -> pd.DataFrame:
    idx = pd.bdate_range("2016-01-01", END)
    n = len(idx)
    df = pd.DataFrame({
        "Copper/Gold": 0.0016 + 0.0002 * np.sin(np.arange(n) / 100),
        "Equal/Cap S&P": 0.3 - 0.00002 * np.arange(n) / 10,
    }, index=idx)
    return df[df.index >= pd.Timestamp(start)] if start else df


def ladder_ratios(start: str | None = None) -> pd.DataFrame:
    idx = pd.bdate_range("2016-01-01", END)
    n = len(idx)
    df = pd.DataFrame({
        "ETH/BTC": 0.05 + 0.01 * np.sin(np.arange(n) / 80),
        "BTC/SPY": 50 + 20 * np.sin(np.arange(n) / 150),
        "SPY/GLD": 2 + 0.3 * np.cos(np.arange(n) / 120),
        "GLD/TLT": 1.5 + 0.2 * np.sin(np.arange(n) / 90),
    }, index=idx)
    return df[df.index >= pd.Timestamp(start)] if start else df
