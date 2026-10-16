import json
import sys
import types

import numpy as np
import pandas as pd
import pytest

import ai_summary
import config
from models import Signal, collect_signals, last_issue_date, signal_changes


# ---------- reference date

@pytest.mark.parametrize("today,expected", [
    ("2026-10-14", "2026-10-13"),  # Wed → Tue
    ("2026-10-13", "2026-10-09"),  # Tue → previous Fri (strictly before today)
    ("2026-10-17", "2026-10-16"),  # Sat → Fri
    ("2026-10-12", "2026-10-09"),  # Mon → Fri
])
def test_last_issue_date(today, expected):
    assert last_issue_date(pd.Timestamp(today)) == pd.Timestamp(expected)


# ---------- changes

def _daily(values, start="2024-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_signal_changes_units_direction_and_ranking():
    rng = np.random.default_rng(1)
    calm = _daily(4 + rng.normal(0, 0.01, 400).cumsum() * 0.1)            # HY OAS-like, in %
    jumpy = calm.copy()
    jumpy.iloc[-3:] += 0.5                                                  # +50bp shock in the last 3 days
    spx = _daily(4000 * np.exp(rng.normal(0.0005, 0.01, 400).cumsum()))  # random walk, like real prices
    since = calm.index[-6]
    changes = signal_changes([
        Signal("Calm spread", calm, "%", True),
        Signal("Shocked spread", jumpy, "%", True),
        Signal("S&P 500", spx, "pct", False, "{:,.0f}"),
    ], since)
    assert changes[0].label == "Shocked spread"                 # most unusual move first
    shocked = changes[0]
    assert shocked.delta_text.endswith("bp") and shocked.delta > 40
    assert shocked.worse is True and abs(shocked.zscore) > 2
    spx_change = next(c for c in changes if c.label == "S&P 500")
    assert spx_change.delta_text.endswith("%")
    assert spx_change.worse is (spx_change.delta < 0)  # falling stocks = riskier


def test_steady_trend_does_not_produce_huge_scores():
    trend = _daily(np.linspace(-0.8, 0.6, 1500))   # constant daily drift: std of moves ~ 0
    flat_then_step = _daily(np.r_[np.full(1495, 5.33), np.full(5, 5.08)])  # policy rate: long flat, then a cut
    trend_move = signal_changes([Signal("Trend", trend, "%", False)], trend.index[-4])[0]
    assert 0.5 < abs(trend_move.zscore) < 2          # a normal-size move for this series (std-based scoring gave ~1e12)
    cut = signal_changes([Signal("Policy rate", flat_then_step, "%", None)], flat_then_step.index[-8])[0]
    assert cut.delta == pytest.approx(-25) and abs(cut.zscore) > 5   # a genuine surprise


def test_signal_without_new_data_is_skipped():
    monthly = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-08-01", "2026-09-01"]))
    assert signal_changes([Signal("CPI", monthly, "%", True)], pd.Timestamp("2026-09-15")) == []


def test_collect_signals_from_fake_fred(fake_fred):
    import data.fred_data as fd
    from models import compute_risk_model, warmup_start
    start = "2021-10-14"
    risk_full = fd.fetch_macro_risk_data(warmup_start(start))
    _, thermo = compute_risk_model(risk_full, start)
    signals = collect_signals(
        val_df=fd.fetch_valuation_data(start), risk_full=risk_full, yield_df=fd.fetch_yield_curve_data(start),
        liquidity_full=fd.fetch_liquidity_data("2020-10-14"), model_inputs=fd.fetch_model_input_series(start), thermo=thermo,
    )
    labels = {s.label for s in signals}
    assert {"Market Risk Level", "Net Liquidity", "10Y – 2Y", "Sahm Rule", "IG OAS", "VIX", "CPI YoY"} <= labels
    since = pd.Timestamp.today().normalize() - pd.Timedelta(days=30)
    changes = signal_changes(signals, since)
    assert changes and all(c.as_of > since for c in changes)


# ---------- AI payload / prompt

def test_ai_prompt_grounds_what_changed_in_computed_changes(monkeypatch, tmp_path):
    captured = {}

    class FakeCompletions:
        def create(self, **kw):
            captured["prompt"] = kw["messages"][0]["content"]
            msg = types.SimpleNamespace(content=json.dumps({"executive_summary": "- ok", "what_changed": "HY spreads widened."}))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = lambda api_key: types.SimpleNamespace(chat=types.SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "get_secret", lambda name: "test-key")

    shocked = Signal("HY OAS", _daily(np.r_[np.full(395, 4.0), np.full(5, 4.6)]), "%", True)
    moves = signal_changes([shocked], shocked.series.index[-8])
    payload = ai_summary.build_macro_signal_payload(
        macro_risk_score=55, readings={"Sahm Rule": "0.27"},
        changes=ai_summary.changes_for_prompt(moves), changes_since="2025-07-01",
    )
    out = ai_summary.generate_ai_summary(payload, [], "2026-10-15")
    assert out["what_changed"] == "HY spreads widened."
    prompt = captured["prompt"]
    assert "CHANGES (computed from the data):" in prompt
    assert "Since 2025-07-01" in prompt and '"signal": "HY OAS"' in prompt and "+60bp" in prompt
    assert '"Sahm Rule": "0.27"' in prompt
    assert "using ONLY the CHANGES section" in prompt


def test_changes_for_prompt_labels_size_and_direction():
    shocked = Signal("VIX", _daily(np.r_[np.full(300, 15.0) + np.sin(np.arange(300)), np.full(3, 30.0)]), "pts", True, "{:.1f}")
    item = ai_summary.changes_for_prompt(signal_changes([shocked], shocked.series.index[-5]))[0]
    assert item == {"signal": "VIX", "now": "30.0", "change": item["change"], "size_vs_typical": "large", "direction": "riskier"}


# ---------- newsletter notes

def test_refresh_what_changed_markdown():
    import refresh
    sig = Signal("10Y – 2Y", _daily(np.linspace(-0.2, 0.3, 300)), "%", False)
    md = refresh.what_changed_markdown(signal_changes([sig], sig.series.index[-6]), pd.Timestamp("2026-10-13"))
    assert md.startswith("# What changed since Tue Oct 13, 2026")
    assert "| 10Y – 2Y |" in md and "bp" in md and "safer" in md
    assert "No signals" in refresh.what_changed_markdown([], pd.Timestamp("2026-10-13"))
