import numpy as np
import pandas as pd
import pytest

from fakes import fred_series
from models import (
    RISK_ZONES,
    change_over,
    compute_macro_risk_composite,
    compute_net_liquidity,
    compute_pillar_scores,
    compute_risk_model,
    compute_risk_thermostat,
    latest_change,
    risk_zone,
    stable_zone_index,
    warmup_start,
)


def mixed_frequency_risk_frame(seed: int = 0) -> pd.DataFrame:
    """Risk pillars at their real frequencies, merged without forward-filling (like data.fred_data)."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2010-01-01", "2026-10-09")
    months = pd.date_range("2010-01-01", "2026-09-01", freq="MS")
    weeks = pd.date_range("2010-01-06", "2026-10-07", freq="W-WED")
    quarters = pd.date_range("2010-01-01", "2026-07-01", freq="QS")
    infl = 0.03 + rng.normal(0, 0.002, len(months)).cumsum() * 0.05
    return pd.DataFrame({
        "GDP": pd.Series(15000 * np.cumprod(1 + 0.005 + rng.normal(0, 0.003, len(quarters))), index=quarters),
        "UNEMPLOYMENT": pd.Series(5 + rng.normal(0, 0.1, len(months)).cumsum() * 0.3, index=months),
        "INFLATION": pd.Series(220 * np.cumprod(1 + infl / 12), index=months),
        "CREDIT_TIGHTENING": pd.Series(rng.normal(0, 0.05, len(weeks)).cumsum() * 0.2 - 0.4, index=weeks),
        "LIQUIDITY": pd.Series(3e6 * np.cumprod(1 + 0.001 + rng.normal(0, 0.003, len(weeks))), index=weeks),
        "CREDIT_STRESS": pd.Series(4 + np.abs(rng.normal(0, 0.05, len(days)).cumsum()) * 0.1, index=days),
    }).dropna(how="all")


# ---------- calendar-based changes

def test_cpi_yoy_uses_calendar_dates_on_mixed_frequency_frame():
    df = pd.DataFrame({"HY": fred_series("BAMLH0A0HYM2"), "CPI": fred_series("CPIAUCSL")}).dropna(how="all")
    cpi = df["CPI"].dropna()
    assert change_over(cpi).iloc[-1] == pytest.approx(3.0, abs=1e-6)
    assert latest_change(cpi) == pytest.approx(3.0, abs=1e-6)
    # The old row-count approach on the forward-filled daily frame measured ~12 days, not a year
    filled = df["CPI"].ffill().dropna()
    assert abs(((filled / filled.shift(12)) - 1).iloc[-1] * 100) < 1.0


def test_latest_change_needs_a_year_of_history():
    cpi = fred_series("CPIAUCSL")
    assert latest_change(cpi.iloc[-6:]) is None
    assert latest_change(None) is None


def test_change_over_difference_mode():
    s = pd.Series([1.0, 1.5, 2.0], index=pd.to_datetime(["2024-01-01", "2024-06-01", "2025-01-01"]))
    assert change_over(s, pct=False).iloc[-1] == pytest.approx(1.0)


# ---------- risk composite / thermostat

def test_inflation_pillar_is_not_biased_by_trending_price_level():
    df = mixed_frequency_risk_frame()
    cpi = df["INFLATION"].dropna()
    level_z = ((cpi - cpi.rolling(36).mean()) / cpi.rolling(36).std()).dropna()
    yoy_z = compute_pillar_scores(df)["INFLATION"].dropna()
    assert (level_z > 0).mean() > 0.85          # old approach: "high inflation risk" almost always
    assert 0.2 < (yoy_z > 0).mean() < 0.8       # new approach: centered


def test_warmup_makes_display_window_complete_and_matches_full_history():
    df = mixed_frequency_risk_frame()
    start = "2021-10-14"
    assert warmup_start(start) == "2016-10-14"
    assert warmup_start(None) is None
    fetched = df[df.index >= pd.Timestamp(warmup_start(start))]
    comp, thermo = compute_risk_model(fetched, start)
    assert (comp.index[0] - pd.Timestamp(start)).days <= 7
    assert (thermo.index[0] - pd.Timestamp(start)).days <= 7
    comp_all, thermo_all = compute_risk_model(df, start)
    pd.testing.assert_series_equal(comp, comp_all.loc[comp.index], check_names=False, atol=1e-9)
    pd.testing.assert_series_equal(thermo, thermo_all.loc[thermo.index], check_names=False, atol=1e-9)


def test_missing_pillar_is_averaged_out_not_counted_as_zero():
    df = mixed_frequency_risk_frame().drop(columns=["GDP"])
    composite = compute_macro_risk_composite(df)
    manual = compute_pillar_scores(df).mean(axis=1).dropna()
    pd.testing.assert_series_equal(composite, manual.loc[composite.index], check_names=False)


def test_thermostat_matches_reference_percentile():
    comp = compute_macro_risk_composite(mixed_frequency_risk_frame())
    fast = compute_risk_thermostat(comp)
    roll = comp.rolling(pd.Timedelta(days=365), min_periods=60)
    slow = roll.apply(lambda x: (x.iloc[-1] > x).mean() * 100, raw=False).dropna().clip(0, 100)
    pd.testing.assert_series_equal(fast, slow.loc[fast.index], check_names=False, atol=1e-9)


# ---------- zones

def test_single_six_zone_scale():
    assert len(RISK_ZONES) == 6
    assert [risk_zone(v) for v in (10, 59.9, 60, 74.9, 75, 90, 100)] == [
        "Very Low Risk", "Moderate Risk", "High Risk", "High Risk", "Very High Risk", "Extreme Risk", "Extreme Risk"]


def test_stable_zones_ignore_short_blips_and_backdate_real_changes():
    idx = pd.bdate_range("2024-01-01", periods=60)
    scores = pd.Series(50.0, index=idx)          # Moderate (zone 2)
    scores.iloc[10:13] = 65                      # 3-day blip into High
    scores.iloc[30:] = 65                        # real move into High
    zones = stable_zone_index(scores, min_obs=10)
    assert (zones.iloc[:30] == 2).all()          # blip ignored
    assert (zones.iloc[30:] == 3).all()          # change dated to day 30, not day 39


# ---------- net liquidity

def test_net_liquidity_units():
    w = pd.date_range("2024-01-03", periods=4, freq="W-WED")
    liq = pd.DataFrame({
        "WALCL": pd.Series(7_000_000.0, index=w),                                   # millions
        "TGA": pd.Series(800_000.0, index=w),                                       # millions
        "RRP": pd.Series(500.0, index=pd.bdate_range("2024-01-01", "2024-01-31")),  # billions
    })
    assert compute_net_liquidity(liq).iloc[-1] == pytest.approx(5_700_000)
    assert compute_net_liquidity(liq.drop(columns=["RRP"])).iloc[-1] == pytest.approx(6_200_000)
    assert compute_net_liquidity(liq.drop(columns=["TGA"])).empty


# ---------- valuation pressure

def test_valuation_index_uses_inflation_rate_not_price_level():
    from models import compute_valuation_pressure_index, rebase_to_window_mean
    months = pd.date_range("2015-01-01", "2026-09-01", freq="MS")
    base = pd.DataFrame({
        "SP500": 4000.0, "UNRATE": 4.0, "FEDFUNDS": 2.0, "M2": 20000.0,
        "INFLATION": 250 * 1.03 ** (np.arange(len(months)) / 12),   # steady 3% inflation, rising price level
    }, index=months)
    vpi = compute_valuation_pressure_index(base)
    assert vpi.index[0] >= months[0] + pd.DateOffset(years=1) - pd.Timedelta(days=1)  # YoY needs a year
    assert vpi.max() / vpi.min() == pytest.approx(1.0, abs=1e-6)                     # flat: level no longer leaks in
    deflation = base.assign(INFLATION=250 * 0.99 ** (np.arange(len(months)) / 12))
    assert (compute_valuation_pressure_index(deflation) == 0).all()                   # floored, not negative
    rebased = rebase_to_window_mean(pd.Series([0.01, 1.0, 2.0]))
    assert rebased.mean() == pytest.approx(100)                                       # tiny first value doesn't blow up
