"""
Regime engine: auto-derives a default set of macro_signals from the FRED-driven
models already built for the Streamlit dashboard (models/macro_risk.py,
config.FRED_MACRO_RISK), and evaluates the offensive/neutral/defensive regime
purely from whatever signals are currently stored (auto-seeded + any manual
edits) — matching the spec's POST /api/regime/evaluate contract of "uses
stored signal states" rather than re-fetching external data on every call.

sync_auto_signals() is meant to be called lazily (e.g. first time a user's
signal list is empty) or from a scheduled job — never from /api/regime/evaluate
itself, since the spec requires that endpoint to work off stored state only.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.orm import Session

import config as dashboard_config
from data import fetch_yield_curve_data, fetch_macro_risk_data, fetch_liquidity_data
from . import models_db as m


def previous_regime(db: Session, user_id: str, current_regime: str) -> str | None:
    """The regime just before the current one, if the most recent history row
    landed on the current regime; else None (no known prior state)."""
    last = (
        db.query(m.RegimeHistory)
        .filter_by(user_id=user_id)
        .order_by(m.RegimeHistory.shifted_at.desc())
        .first()
    )
    if last and last.to_regime == current_regime:
        return last.from_regime
    return None


def posture_since(db: Session, user_id: str, regime: str, fallback: datetime) -> datetime:
    """When the current regime began: the most recent shift *into* it, or
    `fallback` (typically last_evaluated) if it's never shifted on record."""
    last_shift = (
        db.query(m.RegimeHistory)
        .filter_by(user_id=user_id, to_regime=regime)
        .order_by(m.RegimeHistory.shifted_at.desc())
        .first()
    )
    return last_shift.shifted_at if last_shift else fallback

AUTO_SOURCE = "auto:fred"


def _obs_start() -> str | None:
    """3y lookback for auto-signal derivation — enough history for YoY/ROC math
    without pulling full FRED history on every sync."""
    return dashboard_config.lookback_to_observation_start("3y")


def _yoy_pct(series: pd.Series) -> float | None:
    """Date-based YoY %, robust to uneven/mixed-frequency indices. Needed for
    columns from fetch_macro_risk_data, which forward-fills quarterly (GDP),
    monthly (CPI, unemployment) and daily (NFCI, HY OAS) series onto one shared
    index — so counting rows back no longer means a fixed calendar period."""
    s = series.dropna()
    if s.empty or len(s) < 2:
        return None
    last_date, last_val = s.index[-1], s.iloc[-1]
    prior = s.loc[: last_date - pd.DateOffset(years=1)]
    if prior.empty:
        return None
    old_val = prior.iloc[-1]
    if not pd.notna(old_val) or old_val == 0:
        return None
    return float((last_val - old_val) / abs(old_val) * 100)


def _delta_pp(series: pd.Series) -> float | None:
    """Date-based 1y change in percentage points (e.g. unemployment rate)."""
    s = series.dropna()
    if s.empty or len(s) < 2:
        return None
    last_date, last_val = s.index[-1], s.iloc[-1]
    prior = s.loc[: last_date - pd.DateOffset(years=1)]
    if prior.empty:
        return None
    old_val = prior.iloc[-1]
    if not pd.notna(old_val):
        return None
    return float(last_val - old_val)


def _derive_auto_signals() -> list[dict]:
    """Pulls live FRED data and maps it to the spec's signal shape. Best-effort:
    any single series failing does not block the others."""
    out: list[dict] = []

    try:
        yield_df = fetch_yield_curve_data(observation_start=_obs_start())
        if not yield_df.empty and {"DGS10", "DGS3MO"}.issubset(yield_df.columns):
            spread = yield_df["DGS10"].sub(yield_df["DGS3MO"]).dropna()
            if not spread.empty:
                val = float(spread.iloc[-1])
                stance = "bearish" if val < 0 else ("bullish" if val > 1.0 else "neutral")
                out.append({
                    "name": "Yield Curve (10Y-3M)", "category": "rates",
                    "current_value": f"{val:.2f}%", "stance": stance,
                    "notes": "Inverted (<0) has historically preceded recession risk.",
                })
    except Exception:
        pass

    try:
        risk_df = fetch_macro_risk_data(observation_start=_obs_start())
        if not risk_df.empty:
            if "CREDIT_STRESS" in risk_df.columns:
                hy = risk_df["CREDIT_STRESS"].dropna()
                if not hy.empty:
                    val = float(hy.iloc[-1])
                    stance = "bearish" if val >= 5 else ("bullish" if val < 3.5 else "neutral")
                    out.append({
                        "name": "Credit Spreads (HY OAS)", "category": "credit",
                        "current_value": f"{val:.2f}%", "stance": stance,
                        "notes": "Reference: <3.5% calm, >=5% stress rising, >=7% high stress.",
                    })
            if "CREDIT_TIGHTENING" in risk_df.columns:
                nfci = risk_df["CREDIT_TIGHTENING"].dropna()
                if not nfci.empty:
                    val = float(nfci.iloc[-1])
                    stance = "bearish" if val > 0 else "bullish"
                    out.append({
                        "name": "Financial Conditions (NFCI)", "category": "credit",
                        "current_value": f"{val:.3f}", "stance": stance,
                        "notes": "Chicago Fed NFCI; positive = tighter than average conditions.",
                    })
            if "INFLATION" in risk_df.columns:
                cpi = risk_df["INFLATION"].dropna()
                yoy = _yoy_pct(cpi)
                if yoy is not None:
                    stance = "bearish" if yoy > 3.0 else ("bullish" if yoy < 2.0 else "neutral")
                    out.append({
                        "name": "Inflation (CPI YoY)", "category": "inflation",
                        "current_value": f"{yoy:.1f}%", "stance": stance,
                        "notes": "Bearish above ~3% YoY, bullish near/below the 2% target.",
                    })
            if "UNEMPLOYMENT" in risk_df.columns:
                unemp = risk_df["UNEMPLOYMENT"].dropna()
                delta = _delta_pp(unemp)
                if delta is not None:
                    stance = "bearish" if delta > 0.1 else ("bullish" if delta < -0.1 else "neutral")
                    out.append({
                        "name": "Unemployment Rate", "category": "employment",
                        "current_value": f"{unemp.iloc[-1]:.1f}%", "stance": stance,
                        "notes": f"{delta:+.1f}pp vs. 1y ago.",
                    })
            if "GDP" in risk_df.columns:
                gdp = risk_df["GDP"].dropna()
                yoy = _yoy_pct(gdp)
                if yoy is not None:
                    stance = "bullish" if yoy > 2.0 else ("bearish" if yoy < 0 else "neutral")
                    out.append({
                        "name": "Real GDP Growth (YoY)", "category": "growth",
                        "current_value": f"{yoy:.1f}%", "stance": stance,
                        "notes": "Bearish if contracting, bullish if above ~2% trend growth.",
                    })
    except Exception:
        pass

    try:
        liquidity_df = fetch_liquidity_data(observation_start=_obs_start())
        if not liquidity_df.empty and "WALCL" in liquidity_df.columns:
            walcl = liquidity_df["WALCL"].dropna()
            yoy = _yoy_pct(walcl)
            if yoy is not None:
                stance = "bullish" if yoy > 0 else ("bearish" if yoy < -2.0 else "neutral")
                out.append({
                    "name": "Global Liquidity (Fed Balance Sheet YoY)", "category": "liquidity",
                    "current_value": f"{yoy:.1f}%", "stance": stance,
                    "notes": "Expanding balance sheet tends to support risk assets.",
                })
    except Exception:
        pass

    return out


def sync_auto_signals(db: Session, user_id: str) -> int:
    """Upserts the auto-derived signals for a user (matched by name+source).
    Manually-added signals are untouched. Returns the number of signals written."""
    derived = _derive_auto_signals()
    now = datetime.now(timezone.utc)
    n = 0
    for sig in derived:
        existing = (
            db.query(m.MacroSignal)
            .filter_by(user_id=user_id, name=sig["name"], source=AUTO_SOURCE)
            .first()
        )
        if existing:
            existing.current_value = sig["current_value"]
            existing.stance = sig["stance"]
            existing.notes = sig["notes"]
            existing.category = sig["category"]
            existing.last_updated = now
            existing.active = True
        else:
            db.add(m.MacroSignal(
                user_id=user_id, name=sig["name"], category=sig["category"],
                current_value=sig["current_value"], stance=sig["stance"],
                notes=sig["notes"], source=AUTO_SOURCE, active=True,
            ))
        n += 1
    db.commit()
    return n


# Regime thresholds — majority-vote-with-margin over active signal stances.
# Documented here since these numbers are a judgment call, not derived from the spec.
_DEFENSIVE_MARGIN = 2   # bearish - bullish >= this -> defensive
_OFFENSIVE_MARGIN = 2   # bullish - bearish >= this -> offensive
_IMBALANCE_WARN_MARGIN = 3  # gap this large without a regime flip -> "approaching" warning


def tally_signal_counts(db: Session, user_id: str) -> dict:
    signals = db.query(m.MacroSignal).filter_by(user_id=user_id, active=True).all()
    counts = {"bullish": 0, "neutral": 0, "bearish": 0}
    for s in signals:
        if s.stance in counts:
            counts[s.stance] += 1
    return counts


def derive_regime_from_counts(counts: dict) -> tuple[str, str]:
    """Returns (regime, confidence) from bullish/neutral/bearish counts."""
    bullish, neutral, bearish = counts["bullish"], counts["neutral"], counts["bearish"]
    total = bullish + neutral + bearish
    gap = bearish - bullish

    if total == 0:
        return "neutral", "low"
    if gap >= _DEFENSIVE_MARGIN:
        regime = "defensive"
    elif -gap >= _OFFENSIVE_MARGIN:
        regime = "offensive"
    else:
        regime = "neutral"

    ratio = abs(gap) / total
    if ratio >= 0.5:
        confidence = "high"
    elif ratio >= 0.25:
        confidence = "medium"
    else:
        confidence = "low"
    return regime, confidence


def build_summary(regime: str, counts: dict) -> str:
    bullish, neutral, bearish = counts["bullish"], counts["neutral"], counts["bearish"]
    label = {"offensive": "Offensive", "neutral": "Neutral", "defensive": "Defensive"}[regime]
    return (
        f"{label} posture: {bearish} bearish, {neutral} neutral, {bullish} bullish "
        f"across {bullish + neutral + bearish} tracked macro signals."
    )


def is_approaching_shift(counts: dict, regime: str) -> str | None:
    """Returns a warning message if signals are tipping toward a different
    regime without having flipped yet, else None. Used for the Section 4
    'signal imbalance tips significantly' alert."""
    bullish, bearish = counts["bullish"], counts["bearish"]
    gap = bearish - bullish
    if regime != "defensive" and gap >= _IMBALANCE_WARN_MARGIN:
        return f"Macro signals now {bearish} Bearish / {bullish} Bullish — approaching Defensive"
    if regime != "offensive" and -gap >= _IMBALANCE_WARN_MARGIN:
        return f"Macro signals now {bullish} Bullish / {bearish} Bearish — approaching Offensive"
    return None
