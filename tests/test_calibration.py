import numpy as np
import pandas as pd
import pytest

from models.calibration import forward_outcomes, stats_markdown, zone_forward_stats


def test_forward_outcomes_known_values():
    days = pd.date_range("2020-01-01", "2021-12-31", freq="D")
    prices = pd.Series(np.linspace(100, 200, len(days)), index=days)
    prices.loc["2020-02-01":"2020-03-01"] *= 0.8                       # a 20% dip inside the first 6 months
    out = forward_outcomes(prices, pd.DatetimeIndex(["2020-01-01", "2021-11-01"]))
    first = out.iloc[0]
    expected_3m = (prices.asof(pd.Timestamp("2020-04-01")) / 100 - 1) * 100
    assert first["ret_3M"] == pytest.approx(expected_3m)
    assert first["maxdd_6M"] < -10                                    # sees the dip
    assert np.isnan(out.iloc[1]["ret_12M"]) and np.isnan(out.iloc[1]["maxdd_6M"])  # window not complete


def test_zones_separate_outcomes_when_risk_precedes_declines():
    days = pd.bdate_range("2000-01-03", "2019-12-31")
    regime_high = (days.year % 2 == 1)                                 # alternate calm / stressed years
    thermo = pd.Series(np.where(regime_high, 85.0, 10.0), index=days)
    daily_ret = np.where(regime_high, -0.0008, 0.0008)                 # stressed years fall, calm years rise
    prices = pd.Series(100 * np.exp(np.cumsum(daily_ret)), index=days)
    table = zone_forward_stats(thermo, prices)
    assert set(table.index) == {"Very Low Risk", "Very High Risk", "All"}
    assert table.loc["Very Low Risk", "median 3M %"] > 0 > table.loc["Very High Risk", "median 3M %"]
    assert table.loc["Very High Risk", "avg worst 6M drawdown %"] < table.loc["Very Low Risk", "avg worst 6M drawdown %"]
    assert table.loc["All", "weeks"] == table.drop(index="All")["weeks"].sum()
    md = stats_markdown(table, "Test")
    assert md.startswith("# Test") and "| Very High Risk |" in md


def test_calibration_script_end_to_end(fake_fred, monkeypatch, tmp_path):
    import importlib.util

    import config
    import data.market_data as md
    from conftest import ROOT

    days = pd.bdate_range("1995-01-03", "2026-10-09")
    gspc = pd.DataFrame({("^GSPC", "Close"): np.linspace(500, 6600, len(days))}, index=days)
    gspc.columns = pd.MultiIndex.from_tuples(gspc.columns)
    monkeypatch.setattr(md, "_download", lambda tickers, start: gspc)
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path)
    spec = importlib.util.spec_from_file_location("calibrate_zones", ROOT / "scripts" / "calibrate_zones.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    monkeypatch.setattr(script, "_download", lambda tickers, start: gspc)
    assert script.main() == 0
    text = (tmp_path / "zone_calibration.md").read_text(encoding="utf-8")
    assert text.startswith("# Market Risk Level zones vs. S&P 500 outcomes") and "| All |" in text
