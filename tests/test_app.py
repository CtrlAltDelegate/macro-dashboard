"""Headless runs of app.py (Streamlit AppTest) with synthetic FRED data and stubbed Yahoo/RSS — no network."""
import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import config
import data
import news
from conftest import ROOT
from fakes import END, btc_prices, index_history, ladder_ratios, market_ratios

APP = str(ROOT / "app.py")


class _Ctx:
    pass


@pytest.fixture
def offline_markets(monkeypatch, no_ai):
    offline_markets = _Ctx()
    monkeypatch.setattr(data, "fetch_rotation_ladder_data", lambda start=None: ladder_ratios(start))
    monkeypatch.setattr(data, "fetch_market_ratios", lambda start=None: market_ratios(start))
    monkeypatch.setattr(data, "fetch_index_history", index_history)
    monkeypatch.setattr(data, "fetch_bitcoin_data", lambda observation_start=None: btc_prices(observation_start))
    calls = []

    def fake_news(**kw):
        calls.append(kw)
        return [{
            "title": "Your Social Security check will rise $75 a month as inflation cools",
            "source": "Test", "date": "2026-10-14", "link": "", "summary": "Costs $4 more.",
        }]

    monkeypatch.setattr(news, "fetch_recent_macro_news", fake_news)
    offline_markets.news_calls = calls
    st.cache_data.clear()
    yield offline_markets
    st.cache_data.clear()


def run_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def metrics(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def test_app_with_fred_data(fake_fred, offline_markets):
    at = run_app()
    assert not at.error, [e.value for e in at.error]
    m = metrics(at)
    assert m["CPI YoY"] == "3.0%"
    assert m["Core CPI YoY"] == "2.8%"
    assert m["Fed Balance Sheet"] == "$6.60T"
    assert m["Sahm Rule"] == "0.27 pp"
    assert m["Building Permits"].endswith("K") and m["Lending Standards"].endswith("%")
    assert "Growth & Breadth" in [h.value for h in at.header]
    for label in ["Net Liquidity", "IG OAS", "VIX", "Broad Dollar", "10Y Breakeven", "Real GDP YoY",
                  "10Y Term Premium", "30Y Mortgage", "Building Permits", "Lending Standards",
                  "Copper/Gold ×1000", "Equal/Cap S&P"]:
        assert label in m, label
    captions = [c.value for c in at.caption]
    assert f"as of {END:%b %Y}" in captions       # monthly CPI dated by its month, not a day
    assert any(c.startswith("as of Q") for c in captions)  # quarterly GDP
    # 8 macro charts + rotation ladder + 3 fiscal tiles with PNG export
    assert sum(b.label == "Export PNG" for b in at.button) == 12
    # News: dollar amounts rendered literally, not as LaTeX
    assert any("\\$75" in e.label for e in at.expander)
    # Readout includes the new chips
    readout = next(md.value for md in at.markdown if md.value.startswith("<div class=\"readout-panel\""))
    assert "10Y–2Y" in readout and "Sahm Rule" in readout
    # "What changed" strip with a comparison picker and a full table
    assert "What changed" in [h.value for h in at.header]
    assert at.radio[0].options[1:] == ["1 week", "1 month"]
    assert any(e.label.startswith("All ") and "changes since" in e.label for e in at.expander)
    at.radio[0].set_value("1 month").run()
    assert not at.exception


def test_app_without_fred_key_still_shows_yahoo_data(monkeypatch, offline_markets):
    monkeypatch.setattr(config, "FRED_API_KEY", "")
    at = run_app()
    assert any("FRED_API_KEY" in w.value for w in at.warning)
    assert "Rotation Ladder" in [h.value for h in at.subheader]
    assert metrics(at).get("Bitcoin Price", "—") != "—"


def test_pdf_brief_on_demand(fake_fred, offline_markets):
    at = run_app()
    assert "Download PDF" not in [d.label for d in at.get("download_button")]   # not built until asked
    next(b for b in at.button if b.label == "Prepare PDF brief").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Download PDF" in [d.label for d in at.get("download_button")]
    assert not [c.value for c in at.caption if c.value.startswith("PDF could not be generated")]



def test_cards_charts_and_accessibility(fake_fred, offline_markets):
    at = run_app()
    deltas = {m.label: m.delta for m in at.metric if m.delta}
    # Delta text starts with its sign so Streamlit draws the right arrow/color, in sensible units
    assert deltas and all(d[0] in "+-" or d == "unch 1Y" for d in deltas.values()), deltas
    assert deltas["Fed Funds Rate"].endswith("bp 1Y")
    assert deltas["CPI YoY"] == "unch 1Y"                        # fake CPI inflation is a steady 3%
    assert deltas["Unemployment"].endswith("pp 1Y") and deltas["Market Risk Score"].endswith(" 1Y")
    assert deltas["Yield Curve (10Y–3M)"].endswith("bp 1Y")          # not a % change of a spread
    assert deltas["Initial Claims"].endswith("% 1Y")
    # Each macro chart has a text alternative (latest value) or a footer
    latest = [c.value for c in at.caption if c.value.startswith("Latest: ")]
    assert len(latest) >= 7
    # Color-coded chips carry screen-reader text and a visible key
    panel = next(md.value for md in at.markdown if "changes-panel" in md.value and md.value.startswith("<div"))
    assert 'class="sr-only"' in panel
    assert any("Red = adds risk" in md.value for md in at.markdown)
    # One page title; Regimes no longer repeats its cards in a snapshot
    assert [t.value for t in at.title] == ["Macro Dashboard"]
    assert [h.value for h in at.header].count("Today's Snapshot") == 1   # Markets' BTC strip only
    # Headlines are cached, not refetched on every interaction
    at.radio[0].set_value("1 week").run()
    assert len(offline_markets.news_calls) == 1


def test_merged_cycle_and_bear_market_sections(fake_fred, offline_markets):
    at = run_app()
    assert "Bitcoin Cycle Regression Model" in [h.value for h in at.header]
    assert "Historical Bear Markets — S&P 500 / NASDAQ" in [h.value for h in at.subheader]
    labels = {m.label for m in at.metric}
    assert {"Drawdown from cycle top", "Drawdown from all-time high", "Bear markets on record (≥20%)"} <= labels
    # Merged-in metrics use plain captions, not arrow deltas
    assert not [m for m in at.metric if m.label == "Drawdown from all-time high" and m.delta]
    # Cycle charts (x = cycle number) get no date caption; "$" ranges stay literal
    assert not [c.value for c in at.caption if "1970" in c.value]
    bottom = next(m.value for m in at.metric if m.label == "Model 1: projected bottom (band)")
    assert bottom == "—" or "\\$" in bottom
