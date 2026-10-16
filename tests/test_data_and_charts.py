from unittest import mock

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

import data.fred_data as fred_data
import news
from charts.build import (
    add_recession_shading,
    build_all_charts,
    build_bitcoin_chart,
    build_liquidity_chart,
    build_net_liquidity_chart,
    build_oil_chart,
    build_yield_curve_chart,
)
from data.market_data import _extract_closes
from models import change_over, compute_risk_model, warmup_start


# ---------- data layer

def test_fred_frames_are_not_forward_filled(fake_fred):
    df = fred_data.fetch_macro_risk_data("2020-01-01")
    cpi = df["INFLATION"].dropna()
    assert (cpi.index.day == 1).all()  # monthly observations only, not a daily ffilled column
    assert isinstance(df.index, pd.DatetimeIndex)


def test_model_inputs_include_new_series(fake_fred):
    out = fred_data.fetch_model_input_series("2024-01-01")
    for sid in ["DGS2", "CPILFESL", "ICSA", "SAHMREALTIME", "T10YIE", "BAMLC0A0CM", "DTWEXBGS", "VIXCLS"]:
        assert not out[sid].empty, sid


def test_failed_series_becomes_empty_column(fake_fred, monkeypatch):
    monkeypatch.setitem(fred_data.config.FRED_VALUATION, "M2", "NOT_A_SERIES")
    df = fred_data.fetch_valuation_data("2024-01-01")
    assert "M2" in df.columns and df["M2"].isna().all()
    assert isinstance(df.index, pd.DatetimeIndex)


def test_recession_periods_from_usrec():
    usrec = pd.Series([0, 1, 1, 1, 0, 0, 1, 0], index=pd.date_range("2020-01-01", periods=8, freq="MS"), dtype=float)
    with mock.patch.object(fred_data, "_fetch_single", return_value=usrec):
        periods = fred_data.fetch_recession_periods()
    assert periods == [
        (pd.Timestamp("2020-02-01"), pd.Timestamp("2020-04-30")),
        (pd.Timestamp("2020-07-01"), pd.Timestamp("2020-07-31")),
    ]


def test_yahoo_close_extraction_layouts():
    idx = pd.date_range("2024-01-01", periods=5)
    multi = pd.DataFrame(np.arange(20.0).reshape(5, 4), index=idx,
                         columns=pd.MultiIndex.from_product([["BTC-USD", "SPY"], ["Close", "Open"]]))
    out = _extract_closes(multi, ["BTC-USD", "SPY"])
    assert list(out.columns) == ["BTC-USD", "SPY"] and out["SPY"].iloc[0] == 2.0
    single = pd.DataFrame({"Close": [1.0, 2.0], "Open": [0.0, 0.0]}, index=idx[:2])
    assert list(_extract_closes(single, ["BTC-USD"]).columns) == ["BTC-USD"]


@pytest.mark.parametrize("title,keep", [
    ("Bank of America adds a profit miss to the misery of a $1.2 billion government fine", False),
    ("My wife says we can't afford to retire. Do I keep working?", False),
    ("US inflation rises more than expected", True),
    ("Powell signals rate cuts are coming", True),
    ("Treasury yields jump after strong payrolls", True),
    ("Oil prices slide as OPEC boosts output", True),
    ("Nvidia and Cisco confirm multimillion-dollar donations to a White House ballroom", False),
    ("The dollar rallies as traders pare rate bets", True),
    ("U.S. dollar index hits a three-month high", True),
])
def test_macro_headline_filter(title, keep):
    assert bool(news.MACRO_KEYWORDS.search(title)) is keep


# ---------- charts

@pytest.fixture
def frames(fake_fred):
    start = "2021-10-14"
    liq_start = "2020-10-14"
    risk_full = fred_data.fetch_macro_risk_data(warmup_start(start))
    return dict(
        start=start,
        val=fred_data.fetch_valuation_data(start),
        risk_full=risk_full,
        risk=risk_full[risk_full.index >= pd.Timestamp(start)],
        yields=fred_data.fetch_yield_curve_data(start),
        liq_full=fred_data.fetch_liquidity_data(liq_start),
    )


def test_build_all_charts_with_warmed_up_model(frames):
    comp, thermo = compute_risk_model(frames["risk_full"], frames["start"])
    figs = build_all_charts(frames["val"], frames["risk"], frames["yields"], frames["liq_full"], pd.DataFrame(),
                            composite=comp, thermo=thermo, display_start=frames["start"])
    assert len(figs) == 9 and all(f is not None for f in figs)


def test_liquidity_charts_cover_display_window(frames):
    for build in (build_liquidity_chart, build_net_liquidity_chart):
        fig = build(frames["liq_full"], display_start=frames["start"])
        first = pd.Timestamp(fig.data[0].x[0])
        assert 0 <= (first - pd.Timestamp(frames["start"])).days <= 7, build.__name__


def test_oil_cpi_overlay_and_btc_liquidity_overlay(frames):
    oil = pd.DataFrame({"DCOILWTICO": fred_data.fetch_oil_data("2021-10-14")["DCOILWTICO"]})
    fig = build_oil_chart(oil, cpi_series=frames["risk_full"]["INFLATION"])
    cpi_trace = next(t for t in fig.data if t.name == "CPI YoY %")
    assert cpi_trace.y[-1] == pytest.approx(3.0, abs=1e-6)
    assert len(build_oil_chart(oil).data) == 1

    liq_yoy = change_over(frames["liq_full"]["WALCL"])
    btc = pd.Series(np.exp(np.linspace(8, 11, 1000)), index=pd.bdate_range("2022-01-03", periods=1000))
    fig = build_bitcoin_chart(btc, liquidity_yoy_series=liq_yoy)
    trace = next(t for t in fig.data if t.name == "Liquidity YoY %")
    assert trace.y[-1] == pytest.approx(liq_yoy.asof(btc.index[-1]))  # the YoY value itself, not YoY-of-YoY


def test_yield_chart_has_10y2y_and_calendar_momentum(frames):
    fig = build_yield_curve_chart(frames["yields"])
    names = [t.name for t in fig.data]
    assert "10Y – 2Y" in names
    mom = next(t for t in fig.data if t.name == "Spread ROC (90d)")
    spread = (frames["yields"]["DGS10"] - frames["yields"]["DGS3MO"]).dropna()
    expected = spread.iloc[-1] - spread.asof(spread.index[-1] - pd.Timedelta(days=90))
    assert mom.y[-1] == pytest.approx(expected)


def test_recession_shading_clipped_to_data():
    fig = go.Figure(go.Scatter(x=pd.date_range("2020-03-01", "2020-12-31"), y=np.arange(306)))
    add_recession_shading(fig, [(pd.Timestamp("2020-02-01"), pd.Timestamp("2020-04-30")),
                                (pd.Timestamp("2019-01-01"), pd.Timestamp("2019-02-28"))])
    assert len(fig.layout.shapes) == 1
    assert str(fig.layout.shapes[0].x0).startswith("2020-03-01")
