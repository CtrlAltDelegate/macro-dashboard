"""
"What changed" — the dashboard's key signals compared with a reference date.

Changes are computed from the data itself (value now vs. value as of the reference date), so they work
anywhere — no stored snapshots. Each move is also scored against that series' typical move over the
same horizon, so the strip can lead with what is genuinely unusual.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .liquidity import compute_net_liquidity
from .timeseries import change_over


@dataclass
class Signal:
    label: str
    series: pd.Series
    unit: str                      # "%" level in percent (moves in bp), "pct" (moves in %), "pts" (moves in points)
    higher_is_worse: bool | None   # None = direction is neither good nor bad
    fmt: str = "{:.2f}"            # format for the current value


@dataclass
class SignalChange:
    label: str
    now: float
    then: float
    delta: float          # bp for unit "%", % for "pct", points for "pts"
    unit: str
    zscore: float | None  # delta / typical move over the same horizon
    worse: bool | None    # True = moved in the risk-increasing direction
    as_of: pd.Timestamp
    fmt: str

    @property
    def delta_text(self) -> str:
        if self.delta == 0:
            return "unch"
        if self.unit == "%":
            return f"{self.delta:+.0f}bp"
        if self.unit == "pct":
            return f"{self.delta:+.1f}%"
        return f"{self.delta:+.2f}"

    @property
    def now_text(self) -> str:
        return self.fmt.format(self.now)


def last_issue_date(today: pd.Timestamp | None = None) -> pd.Timestamp:
    """Most recent Tuesday or Friday strictly before today (the newsletter schedule)."""
    d = (today or pd.Timestamp.today()).normalize() - pd.Timedelta(days=1)
    while d.weekday() not in (1, 4):
        d -= pd.Timedelta(days=1)
    return d


def _col(df: pd.DataFrame | None, col: str) -> pd.Series | None:
    if df is None or df.empty or col not in df.columns:
        return None
    s = df[col].dropna()
    return s if not s.empty else None


def collect_signals(
    *,
    val_df: pd.DataFrame | None = None,
    risk_full: pd.DataFrame | None = None,
    yield_df: pd.DataFrame | None = None,
    liquidity_full: pd.DataFrame | None = None,
    model_inputs: dict[str, pd.Series] | None = None,
    thermo: pd.Series | None = None,
    btc: pd.Series | None = None,
    oil_df: pd.DataFrame | None = None,
    market_ratios: pd.DataFrame | None = None,
) -> list[Signal]:
    """The dashboard's headline signals, from whatever data is available."""
    mi = model_inputs or {}
    out: list[tuple] = []
    spread = None
    d10, d3 = _col(yield_df, "DGS10"), _col(yield_df, "DGS3MO")
    if d10 is not None and d3 is not None:
        spread = (d10 - d3).dropna()
    net_liq = compute_net_liquidity(liquidity_full) if liquidity_full is not None else None
    cpi = _col(risk_full, "INFLATION")
    out += [
        ("Market Risk Level", thermo, "pts", True, "{:.0f}/100"),
        ("Net Liquidity", net_liq / 1e6 if net_liq is not None and not net_liq.empty else None, "pct", False, "${:.2f}T"),
        ("10Y – 3M", spread, "%", False, "{:.2f}%"),
        ("10Y – 2Y", _col(yield_df, "T10Y2Y"), "%", False, "{:.2f}%"),
        ("10Y Treasury", d10, "%", None, "{:.2f}%"),
        ("10Y Breakeven", mi.get("T10YIE"), "%", True, "{:.2f}%"),
        ("10Y Term Premium", mi.get("THREEFYTP10"), "%", True, "{:.2f}%"),
        ("30Y Mortgage", mi.get("MORTGAGE30US"), "%", True, "{:.2f}%"),
        ("CPI YoY", change_over(cpi) if cpi is not None else None, "%", True, "{:.1f}%"),
        ("Unemployment", _col(risk_full, "UNEMPLOYMENT"), "%", True, "{:.1f}%"),
        ("Sahm Rule", mi.get("SAHMREALTIME"), "pts", True, "{:.2f}"),
        ("HY OAS", _col(risk_full, "CREDIT_STRESS"), "%", True, "{:.2f}%"),
        ("IG OAS", mi.get("BAMLC0A0CM"), "%", True, "{:.2f}%"),
        ("NFCI", _col(risk_full, "CREDIT_TIGHTENING"), "pts", True, "{:.3f}"),
        ("Lending Standards", mi.get("DRTSCILM"), "pts", True, "{:+.1f}%"),
        ("Building Permits", mi.get("PERMIT"), "pct", False, "{:,.0f}K"),
        ("VIX", mi.get("VIXCLS"), "pts", True, "{:.1f}"),
        ("Broad Dollar", mi.get("DTWEXBGS"), "pct", True, "{:.1f}"),
        ("S&P 500", _col(val_df, "SP500"), "pct", False, "{:,.0f}"),
        ("Copper/Gold ×1000", _col(market_ratios, "Copper/Gold") * 1000 if _col(market_ratios, "Copper/Gold") is not None else None, "pct", False, "{:.2f}"),
        ("Equal/Cap S&P", _col(market_ratios, "Equal/Cap S&P"), "pct", False, "{:.3f}"),
        ("Bitcoin", btc, "pct", None, "${:,.0f}"),
        ("WTI Oil", _col(oil_df, "DCOILWTICO"), "pct", None, "${:.2f}"),
    ]
    return [
        Signal(label, s.dropna(), unit, worse, fmt)
        for label, s, unit, worse, fmt in out
        if s is not None and not s.dropna().empty
    ]


def _move(series: pd.Series, horizon: pd.Timedelta, unit: str) -> pd.Series:
    """Historical changes over `horizon`, in the signal's display units."""
    if unit == "pct":
        return change_over(series, horizon)
    moves = change_over(series, horizon, pct=False)
    return moves * 100 if unit == "%" else moves


def signal_changes(signals: list[Signal], since: pd.Timestamp) -> list[SignalChange]:
    """Each signal's change since `since`, largest unusual moves first. Signals without data at `since` are skipped."""
    since = pd.Timestamp(since)
    changes = []
    for sig in signals:
        s = sig.series
        if s.index[-1] <= since:
            continue  # no new observation since the reference date
        then = s.asof(since)
        if pd.isna(then):
            continue
        now = float(s.iloc[-1])
        if sig.unit == "pct":
            if then == 0:
                continue
            delta = (now - then) / abs(then) * 100
        else:
            delta = (now - then) * (100 if sig.unit == "%" else 1)
        # Moves smaller than the display precision count as unchanged (no "-0bp" with a red/green color)
        if abs(delta) < {"%": 0.5, "pct": 0.05}.get(sig.unit, 0.005):
            delta = 0.0
        horizon = s.index[-1] - since
        hist = _move(s, horizon, sig.unit) if horizon >= pd.Timedelta(days=1) else pd.Series(dtype=float)
        # Typical move size = root-mean-square of past moves over the same horizon. Unlike the standard
        # deviation it includes drift, so steady-trending series don't get a near-zero yardstick (and huge scores).
        typical = float(np.sqrt(np.mean(np.square(hist.to_numpy())))) if len(hist) >= 20 else np.nan
        z = float(delta / typical) if typical and np.isfinite(typical) and typical > 0 else None
        worse = None if sig.higher_is_worse is None or delta == 0 else bool((delta > 0) == sig.higher_is_worse)
        changes.append(SignalChange(sig.label, now, float(then), float(delta), sig.unit, z, worse, s.index[-1], sig.fmt))
    return sorted(changes, key=lambda c: -abs(c.zscore) if c.zscore is not None else 0.0)
