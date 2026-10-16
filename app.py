"""
Macro Dashboard — Private, local-first. Run: streamlit run app.py
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from dotenv import load_dotenv

load_dotenv()
import streamlit as st

import config  # reads FRED/OpenAI keys from env, .env, or Streamlit Secrets

log = logging.getLogger("macro_dashboard")

# Server-side log: appears in Streamlit Cloud "Manage app" → Logs (not in browser console)
print(f"[Macro Dashboard] FRED_API_KEY set: {bool(config.FRED_API_KEY)}, OPENAI_API_KEY set: {bool(config.OPENAI_API_KEY)}")

from charts.build import (
    build_valuation_chart,
    build_macro_risk_chart,
    build_yield_curve_chart,
    build_liquidity_chart,
    build_net_liquidity_chart,
    build_fci_chart,
    build_credit_spreads_chart,
    build_thermostat_chart,
    build_curves_chart,
    build_oil_chart,
    build_bitcoin_chart,
    build_bands_chart,
    build_rotation_ladder_chart,
    build_btc_rainbow_chart,
    build_macro_radar_chart,
    build_deficit_pct_gdp_chart,
    build_debt_to_gdp_chart,
    build_interest_burden_chart,
    add_recession_shading,
)
from data import (
    fetch_valuation_data,
    fetch_macro_risk_data,
    fetch_yield_curve_data,
    fetch_liquidity_data,
    fetch_rotation_ladder_data,
    fetch_oil_data,
    fetch_bitcoin_data,
    fetch_real_yield_data,
    fetch_fiscal_data,
    fetch_model_input_series,
    fetch_recession_periods,
)
from models import (
    compute_risk_model,
    compute_net_liquidity,
    collect_signals,
    signal_changes,
    last_issue_date,
    warmup_start,
    risk_zone,
    prepare_regime_curves,
    change_over,
    latest_change,
)
from models.btc_metrics import compute_btc_snapshot

try:
    from pdf_report import build_dashboard_pdf, pdf_available
except ImportError:
    build_dashboard_pdf = None
    pdf_available = lambda: False
try:
    from news import fetch_recent_macro_news, rank_macro_relevance
except ImportError:
    fetch_recent_macro_news = lambda *a, **k: []
    rank_macro_relevance = lambda x, max_return=5: x[:max_return]
try:
    from ai_summary import build_macro_signal_payload, changes_for_prompt, generate_ai_summary, ai_summary_available
except ImportError:
    build_macro_signal_payload = lambda **k: {}
    changes_for_prompt = lambda changes, limit=8: []
    generate_ai_summary = lambda *a, **k: None
    ai_summary_available = lambda: False

try:
    from plotly_export import export_plotly_to_png_or_error
except ImportError:
    def export_plotly_to_png_or_error(fig, *, width=800, height=450):
        return None, "plotly_export not available"


@st.cache_data(show_spinner=False, max_entries=64)
def _png_from_json(fig_json: str) -> tuple[bytes | None, str | None]:
    """Render a figure (passed as JSON so it hashes cheaply) to PNG. Cached so unchanged charts aren't re-exported."""
    return export_plotly_to_png_or_error(pio.from_json(fig_json), width=800, height=450)


def _png_export(fig, file_name: str, key: str) -> None:
    """'Export PNG' renders only when clicked, then offers the download (stays available on later reruns)."""
    flag = f"png_requested_{key}"
    if st.button("Export PNG", key=f"prep_{key}"):
        st.session_state[flag] = True
    if not st.session_state.get(flag):
        return
    with st.spinner("Rendering PNG…"):
        png, err = _png_from_json(fig.to_json())
    if png is not None:
        st.download_button("Download PNG", data=png, file_name=file_name, mime="image/png", key=f"dl_{key}")
    else:
        st.caption(f"PNG export unavailable: {err}")


def _fig_for_pdf(fig):
    """Return a copy of the figure with a light, print-friendly theme for the PDF report."""
    if fig is None:
        return None
    try:
        pdf_fig = go.Figure(fig)
        pdf_fig.update_layout(
            template="plotly_white",
            paper_bgcolor="white",
            plot_bgcolor="#fafafa",
            font=dict(color="#333333", size=11),
        )
        return pdf_fig
    except Exception:
        return fig


st.set_page_config(
    page_title="Macro Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Attractive UI: institutional dark theme, card sections, typography
st.markdown("""
<style>
    /* Container */
    .stApp { max-width: 1400px; margin: 0 auto; padding: 0 1rem 2rem; }
    /* Header */
    h1 {
        font-size: 1.75rem;
        font-weight: 700;
        color: #e6edf3;
        letter-spacing: -0.02em;
        margin-bottom: 0.25rem;
    }
    .subtitle {
        color: #8b949e;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }
    /* Chart sections as cards */
    div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stPlotlyChart"]) {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 1.25rem;
        margin: 1rem 0;
    }
    /* Section titles */
    h2 {
        font-size: 1.15rem;
        font-weight: 600;
        color: #e6edf3;
        margin-top: 1.75rem;
        margin-bottom: 0.25rem;
    }
    .section-desc {
        color: #8b949e;
        font-size: 0.875rem;
        margin-bottom: 1rem;
        line-height: 1.45;
    }
    /* Metrics row */
    [data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 600; color: #58a6ff; }
    /* Buttons */
    .stDownloadButton > button {
        border-radius: 8px;
        border: 1px solid #30363d;
        font-weight: 500;
    }
    /* Footer */
    .footer {
        margin-top: 2.5rem;
        padding-top: 1rem;
        border-top: 1px solid #30363d;
        color: #8b949e;
        font-size: 0.8rem;
    }
    .footer a { color: #58a6ff; text-decoration: none; }
    .footer a:hover { text-decoration: underline; }
    /* Readout panel chips */
    .readout-panel { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-bottom: 1.25rem; padding: 0.75rem 1rem; background: #161b22; border: 1px solid #30363d; border-radius: 10px; }
    .readout-chip { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.25rem 0.6rem; border-radius: 6px; font-size: 0.8rem; font-weight: 500; }
    .readout-chip--neutral { background: #21262d; color: #8b949e; border: 1px solid #30363d; }
    .readout-chip--green { background: rgba(63, 185, 80, 0.2); color: #3fb950; border: 1px solid rgba(63, 185, 80, 0.4); }
    .readout-chip--red { background: rgba(248, 81, 73, 0.2); color: #f85149; border: 1px solid rgba(248, 81, 73, 0.4); }
    .readout-chip--yellow { background: rgba(210, 153, 34, 0.2); color: #d29922; border: 1px solid rgba(210, 153, 34, 0.4); }
    .readout-label { color: #8b949e; font-size: 0.75rem; margin-right: 0.15rem; }
    /* Today's Snapshot per tab */
    .snapshot-panel { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.25rem; }
    .snapshot-title { font-size: 0.8rem; font-weight: 600; color: #8b949e; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.03em; }
</style>
""", unsafe_allow_html=True)

st.markdown("# Macro Dashboard")
st.markdown('<p class="subtitle">Macro (Core) · Markets (Oil, BTC) · Regimes & Bands · Fiscal</p>', unsafe_allow_html=True)


def _roc_1y(series: pd.Series | None) -> float | None:
    """1-year rate of change in percent, by calendar date (works for any frequency / ffilled data)."""
    return latest_change(series)


def _md(text: str) -> str:
    """Escape '$' so Streamlit markdown doesn't render dollar amounts as LaTeX math."""
    return (text or "").replace("$", "\\$")


def _metric_note(label: str, value: str, note: str = "") -> None:
    """A metric with a plain caption. (Passing a label as `delta` adds a colored ↑ arrow it hasn't earned.)"""
    st.metric(label, value)
    if note:
        st.caption(note)


def _as_of(series: pd.Series | None) -> str:
    """Date of the latest observation, at the series' own granularity ('Sep 2026', 'Q3 2026', 'Oct 9')."""
    if series is None:
        return ""
    s = series.dropna()
    if s.empty:
        return ""
    d = s.index[-1]
    gap = s.index.to_series().diff().dt.days.tail(6).median() if len(s) > 1 else 1
    if gap >= 300:
        return f"{d.year}"
    if gap >= 80:
        return f"Q{d.quarter} {d.year}"
    if gap >= 25:
        return f"{d:%b %Y}"
    return f"{d:%b} {d.day}"


def _model_input_cards(items: list[tuple]) -> None:
    """Render a row of model input cards.
    Each item: (label, value_str, roc_1y or None, higher_is_worse[, series]) — with a series, shows its as-of date."""
    if not items:
        return
    cols = st.columns(6)  # fixed grid so cards line up across groups and tabs
    for i, (label, value_str, roc, higher_is_worse, *rest) in enumerate(items):
        with cols[i % len(cols)]:
            delta_str = f"1Y ROC {roc:+.1f}%" if roc is not None else None
            delta_color = "inverse" if higher_is_worse else "normal"  # inverse: positive ROC = red
            st.metric(label, value_str, delta=delta_str, delta_color=delta_color if delta_str else "off")
            as_of = _as_of(rest[0]) if rest else ""
            if as_of:
                st.caption(f"as of {as_of}")

if not config.FRED_API_KEY:
    # Brief diagnostic (no secret values): helps debug Streamlit Cloud Secrets
    has_secrets = fred_in_secrets = False
    try:
        if hasattr(st, "secrets"):
            keys = getattr(st.secrets, "keys", None)
            secret_keys = list(keys()) if keys else []
            has_secrets = len(secret_keys) > 0
            fred_in_secrets = "FRED_API_KEY" in secret_keys
    except Exception:
        pass
    st.warning(
        "Set **FRED_API_KEY** in your environment (or `.env`) to load macro data. "
        "[Get a free key](https://fred.stlouisfed.org/docs/api/api_key.html)."
    )
    with st.expander("Diagnostic (no keys shown)"):
        st.write(f"- Secrets available: **{has_secrets}**")
        st.write(f"- `FRED_API_KEY` in Secrets: **{fred_in_secrets}**")
        st.write("**Where to see server logs:** On your app page, click **Manage app** (bottom-right). In the panel that opens, check the **Logs** tab. You should see a line like `[Macro Dashboard] FRED_API_KEY set: True/False` when the app runs—that’s the server-side truth. (Browser Console / F12 is client-side and will not show this.)")
        st.write("If the log says `False` or you don’t see that line, push this repo, add the key in Settings → Secrets as `FRED_API_KEY = \"...\"`, then **Reboot** the app.")

# Sidebar: refresh, lookback, overlays and toggles
with st.sidebar:
    st.subheader("Data")
    lookback = st.selectbox("Macro lookback", config.LOOKBACK_OPTIONS, index=2)  # 5y default
    show_market_overlay = st.checkbox("Show Market Overlay (S&P 500)", value=False)
    show_10y_3m_lines = st.checkbox("Show 10Y and 3M lines (Yield Curve)", value=False)
    show_event_markers = st.checkbox("Show event markers", value=False)
    st.subheader("Markets")
    oil_log_scale = st.checkbox("Oil: log scale", value=False)
    oil_show_yoy = st.checkbox("Oil: show YoY %", value=False)
    oil_show_cpi = st.checkbox("Oil: show CPI YoY overlay", value=False)
    btc_log_scale = st.checkbox("Bitcoin: log scale", value=True)
    btc_show_liquidity = st.checkbox("Bitcoin: overlay Liquidity YoY", value=False)
    btc_show_real_yield = st.checkbox("Bitcoin: overlay Real yields (10Y TIPS)", value=False)
    btc_rainbow_k = st.slider("BTC Rainbow band width (k σ)", min_value=0.25, max_value=3.0, value=2.0, step=0.25, help="Terminal price proxy = midline − k×stdev. Regression uses full history.")
    st.caption("BTC regression uses full history for stability; chart display follows lookback.")
    st.subheader("Regimes & Bands")
    spx_log_scale = st.checkbox("SPX Regime Bands: log scale", value=False)
    use_fred_only_last_chart = st.checkbox(
        "Use FRED-only for final chart (no Yahoo)",
        value=False,
        help="Show Macro Regime (FRED) instead of Rotation Ladder when Yahoo is blocked.",
    )
    st.subheader("AI & News")
    enable_ai = st.checkbox(
        "Enable AI Interpretation",
        value=bool(config.OPENAI_API_KEY),
        help="Show AI-generated executive summary and interpretation. Requires OPENAI_API_KEY.",
    )
    include_macro_drivers = st.checkbox("Include Macro Drivers headlines", value=True, help="Show 3–5 recent macro-relevant headlines.")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

def _year_before(start: str | None) -> str | None:
    """One year before `start`: YoY series need that much extra history to cover the whole window."""
    return (pd.Timestamp(start) - pd.DateOffset(years=1)).date().isoformat() if start else None


def _from(obj, start: str | None):
    """Rows on/after `start` (None = everything)."""
    if start is None or obj is None or len(obj) == 0:
        return obj
    return obj[obj.index >= pd.Timestamp(start)]


@st.cache_data(ttl=3600, show_spinner="Loading FRED and market data…")
def load_all(lookback: str) -> dict:
    """Fetch everything in parallel. Yahoo-backed data (rotation ladder, BTC) loads even without a FRED key."""
    obs_start = config.lookback_to_observation_start(lookback)
    tasks = {
        "ladder": lambda: fetch_rotation_ladder_data(start=obs_start),
        # Full history: the WMAs (up to 300 weeks) and the rainbow regression need it; charts trim to the
        # lookback. FRED first, Yahoo fallback (also used when there is no FRED key).
        "btc": lambda: fetch_bitcoin_data(observation_start=None),
    }
    if config.FRED_API_KEY:
        tasks.update({
            "val": lambda: fetch_valuation_data(observation_start=obs_start),
            # Extra history so the composite / thermostat are warmed up on the first displayed day
            "risk_full": lambda: fetch_macro_risk_data(observation_start=warmup_start(obs_start)),
            "yield": lambda: fetch_yield_curve_data(observation_start=obs_start),
            "liquidity_full": lambda: fetch_liquidity_data(observation_start=_year_before(obs_start)),
            "oil": lambda: fetch_oil_data(observation_start=obs_start),
            "real_yield": lambda: fetch_real_yield_data(observation_start=obs_start),
            "fiscal": lambda: fetch_fiscal_data(observation_start=obs_start),
            "model_inputs": lambda: fetch_model_input_series(observation_start=_year_before(obs_start)),
            "recessions": lambda: fetch_recession_periods(observation_start=obs_start),
        })
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {name: pool.submit(fn) for name, fn in tasks.items()}
    out = {}
    for name, fut in futures.items():
        try:
            out[name] = fut.result()
        except Exception as e:  # one failed source shouldn't blank the dashboard
            log.warning("load_all: %s failed: %s", name, e)
            out[name] = None
    return out


@st.cache_data(ttl=3600)
def compute_risk(risk_full: pd.DataFrame, display_start: str | None) -> tuple[pd.Series, pd.Series]:
    """(composite, Market Risk Level 0–100), warmed up on the extra history and trimmed to the lookback.
    Cached: shared by the readout, charts, bands and AI payload."""
    if risk_full.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    return compute_risk_model(risk_full, display_start)


_data = load_all(lookback)
_empty_df, _empty_s = pd.DataFrame(), pd.Series(dtype=float)
val_df = _data.get("val") if _data.get("val") is not None else _empty_df
risk_full = _data.get("risk_full") if _data.get("risk_full") is not None else _empty_df
yield_df = _data.get("yield") if _data.get("yield") is not None else _empty_df
liquidity_full = _data.get("liquidity_full") if _data.get("liquidity_full") is not None else _empty_df
oil_df = _data.get("oil") if _data.get("oil") is not None else _empty_df
fiscal_df = _data.get("fiscal") if _data.get("fiscal") is not None else _empty_df
ladder_df = _data.get("ladder") if _data.get("ladder") is not None else _empty_df
btc_series = _data.get("btc") if _data.get("btc") is not None else _empty_s
real_yield_series = _data.get("real_yield") if _data.get("real_yield") is not None else _empty_s
model_input_series = _data.get("model_inputs") or {}
recession_periods = _data.get("recessions") or []

obs_start = config.lookback_to_observation_start(lookback)
# Display windows: risk data was fetched with a warm-up, liquidity a year early (for YoY)
risk_df = _from(risk_full, obs_start)
liquidity_df = _from(liquidity_full, obs_start)

_failed = [name for name, value in _data.items() if value is None]
if _failed:
    st.warning(f"Some data sources failed to load ({', '.join(_failed)}); charts that need them are hidden. See server logs.")

# Optional S&P 500 overlay (SPX/SP500 from valuation data), aligned to each chart's lookback
overlay_val = None
overlay_risk = None
if show_market_overlay and not val_df.empty and "SP500" in val_df.columns:
    s = val_df["SP500"].dropna()
    if not s.empty and s.iloc[0] != 0:
        overlay_val = (s / s.iloc[0]) * 100
    if not risk_df.empty and overlay_val is not None:
        aligned = val_df["SP500"].reindex(risk_df.index).ffill().dropna()
        if not aligned.empty and aligned.iloc[0] != 0:
            overlay_risk = (aligned / aligned.iloc[0]) * 100

# Composite + Thermo (0-100) for the risk charts, Regimes bands and readout
composite_series, thermo_series = compute_risk(risk_full, obs_start)
net_liquidity_series = _from(compute_net_liquidity(liquidity_full), obs_start)


def _plot(fig, key: str, shade_recessions: bool = True) -> None:
    """Render a chart, with NBER recession shading on time-series charts (also kept in PNG exports)."""
    if shade_recessions:
        add_recession_shading(fig, recession_periods)
    st.plotly_chart(fig, width="stretch", key=key)

# Liquidity YoY (WALCL) for readout, model inputs and BTC overlay
liquidity_yoy_series = None
if not liquidity_full.empty and "WALCL" in liquidity_full.columns:
    liquidity_yoy_series = _from(change_over(liquidity_full["WALCL"]), obs_start)
    if liquidity_yoy_series.empty:
        liquidity_yoy_series = None
# BTC is fetched with full history (for WMAs / regression); charts show the lookback window
btc_display = btc_series[btc_series.index >= pd.Timestamp(obs_start)] if obs_start and not btc_series.empty else btc_series
# CPI for oil overlay (from macro risk INFLATION = CPIAUCSL)
cpi_series = risk_full["INFLATION"].dropna() if not risk_full.empty and "INFLATION" in risk_full.columns else None  # history for YoY
# BTC snapshot (WMAs, ROC, distances, Balanced/Terminal); terminal_k from sidebar
btc_snapshot = compute_btc_snapshot(btc_series, terminal_k=btc_rainbow_k) if btc_series is not None and not btc_series.empty else {}
# Oil snapshot (current WTI, 4W ROC, 52W ROC)
oil_snapshot = {}
if not oil_df.empty and "DCOILWTICO" in oil_df.columns:
    oil_price = oil_df["DCOILWTICO"].dropna()
    if len(oil_price) >= 2:
        oil_snapshot["price"] = float(oil_price.iloc[-1])
        oil_snapshot["roc4w"] = latest_change(oil_price, pd.Timedelta(weeks=4))
        oil_snapshot["roc52w"] = latest_change(oil_price)


# ----- Current Readout Panel -----
def _readout_chip(label: str, value: str, style: str = "neutral", title: str = "") -> str:
    value = value.replace("$", "&#36;")  # keep "$" out of Streamlit's LaTeX parsing
    tip = f' title="{title}"' if title else ""
    return f'<span class="readout-chip readout-chip--{style}"{tip}><span class="readout-label">{label}</span>{value}</span>'


macro_score = ""
zone_label = ""
liquidity_status = ""
yield_status = ""
yield_mom_status = ""
fci_status = ""
credit_status = ""

if not thermo_series.empty:
    latest_thermo = thermo_series.iloc[-1]
    macro_score = f"{latest_thermo:.0f}/100"
    zone_label = risk_zone(latest_thermo)

if liquidity_yoy_series is not None:
    liquidity_status = "Expanding" if liquidity_yoy_series.iloc[-1] >= 0 else "Contracting"

last_spread_val = None
last_roc_90_val = None
if not yield_df.empty and "DGS10" in yield_df.columns and "DGS3MO" in yield_df.columns:
    spread = yield_df["DGS10"].sub(yield_df["DGS3MO"]).dropna()
    if not spread.empty:
        last_spread_val = spread.iloc[-1]
        yield_status = "Inverted" if last_spread_val < 0 else "Normal"
        last_roc_90_val = latest_change(spread, pd.Timedelta(days=90), pct=False)
        if last_roc_90_val is not None:
            yield_mom_status = "Steepening" if last_roc_90_val > 0 else "Flattening"

last_10y2y_val = None
if not yield_df.empty and "T10Y2Y" in yield_df.columns:
    _t = yield_df["T10Y2Y"].dropna()
    if not _t.empty:
        last_10y2y_val = float(_t.iloc[-1])

if not risk_df.empty and "CREDIT_TIGHTENING" in risk_df.columns:
    nfci = risk_df["CREDIT_TIGHTENING"].dropna()
    if not nfci.empty:
        fci_status = "Tight" if nfci.iloc[-1] > 0 else "Easy"

if not risk_df.empty and "CREDIT_STRESS" in risk_df.columns:
    hy = risk_df["CREDIT_STRESS"].dropna()
    if not hy.empty:
        s = hy.iloc[-1]
        if s < 4:
            credit_status = "Low"
        elif s < 6:
            credit_status = "Moderate"
        else:
            credit_status = "High"

# Build readout chips (only show when we have data)
chips = []
if macro_score and zone_label:
    chips.append(_readout_chip("Macro Risk", f"{macro_score} ({zone_label})", "neutral"))
if liquidity_status:
    chips.append(_readout_chip("Liquidity", liquidity_status, "green" if liquidity_status == "Expanding" else "red"))
if yield_status and last_spread_val is not None:
    chips.append(_readout_chip("Yield Curve", f"{last_spread_val:.2f}% ({yield_status})", "red" if yield_status == "Inverted" else "green"))
if last_10y2y_val is not None:
    chips.append(_readout_chip("10Y–2Y", f"{last_10y2y_val:.2f}%", "red" if last_10y2y_val < 0 else "green"))
if yield_mom_status and last_roc_90_val is not None:
    chips.append(_readout_chip("YC Momentum", f"{last_roc_90_val:.2f} ({yield_mom_status})", "green" if yield_mom_status == "Steepening" else "yellow"))
if fci_status:
    chips.append(_readout_chip("Financial Conditions", fci_status, "red" if fci_status == "Tight" else "green"))
if credit_status:
    chip_style = "red" if credit_status == "High" else "yellow" if credit_status == "Moderate" else "green"
    chips.append(_readout_chip("Credit Stress", credit_status, chip_style))
_sahm = model_input_series.get("SAHMREALTIME")
if _sahm is not None and not _sahm.dropna().empty:
    _sv = float(_sahm.dropna().iloc[-1])  # >= 0.5 pp has marked the start of every recession since 1970
    chips.append(_readout_chip("Sahm Rule", f"{_sv:.2f} (trigger 0.50)", "red" if _sv >= 0.5 else "yellow" if _sv >= 0.3 else "green"))

if chips:
    st.markdown('<div class="readout-panel">' + "".join(chips) + "</div>", unsafe_allow_html=True)

# ----- What changed (computed from the data: value now vs. value at the reference date) -----
_signals = collect_signals(
    val_df=val_df, risk_full=risk_full, yield_df=yield_df, liquidity_full=liquidity_full,
    model_inputs=model_input_series, thermo=thermo_series, btc=btc_series, oil_df=oil_df,
)
_today = pd.Timestamp(date.today())
_last_issue = last_issue_date(_today)
_since_options = {
    f"Since last issue ({_last_issue:%a %b} {_last_issue.day})": _last_issue,
    "1 week": _today - pd.Timedelta(weeks=1),
    "1 month": _today - pd.DateOffset(months=1),
}
changes_since = None
signal_moves = []
if _signals:
    st.markdown("#### What changed")
    _since_label = st.radio("Compare with", list(_since_options), horizontal=True,
                            label_visibility="collapsed", key="changes_since")
    changes_since = _since_options[_since_label]
    signal_moves = signal_changes(_signals, changes_since)
    if signal_moves:
        _chips = []
        for c in signal_moves[:8]:
            style = "neutral" if c.worse is None else ("red" if c.worse else "green")
            arrow = "▲" if c.delta > 0 else "▼" if c.delta < 0 else "■"
            unusual = c.zscore is not None and abs(c.zscore) >= 2
            tip = f"{abs(c.zscore):.1f}× a typical move over this period" if c.zscore is not None else ""
            _chips.append(_readout_chip(c.label, f"{c.now_text} {arrow} {c.delta_text}" + (" · unusual" if unusual else ""), style, tip))
        st.markdown('<div class="readout-panel">' + "".join(_chips) + "</div>", unsafe_allow_html=True)
        with st.expander(f"All {len(signal_moves)} changes since {changes_since:%b} {changes_since.day} (largest relative to normal first)"):
            st.dataframe(pd.DataFrame([{
                "Signal": c.label,
                "Now": c.now_text,
                "Change": c.delta_text,
                "vs. typical": f"{abs(c.zscore):.1f}×" if c.zscore is not None else "—",
                "Direction": "—" if c.worse is None else ("riskier" if c.worse else "safer"),
                "Latest data": f"{c.as_of:%b} {c.as_of.day}, {c.as_of.year}",
            } for c in signal_moves]), hide_index=True)
    else:
        st.caption(f"No new data since {changes_since:%b} {changes_since.day}.")

# ----- AI Interpretation + Macro Drivers -----
ai_result = None
macro_drivers_list = []
if include_macro_drivers:
    with st.spinner("Fetching macro headlines…"):
        _news = fetch_recent_macro_news(max_articles=12, max_age_days=7)
        macro_drivers_list = rank_macro_relevance(_news, max_return=5)

def _btc_zone(snapshot: dict) -> str | None:
    """Where BTC sits vs. its log-regression midline (Balanced) and lower band (Terminal)."""
    price, mid, low = snapshot.get("price"), snapshot.get("balanced_price"), snapshot.get("terminal_price")
    if price is None or mid is None:
        return None
    if low is not None and price < low:
        return "below terminal band"
    return "below midline" if price < mid else "above midline"


def _last(df: pd.DataFrame, col: str) -> float | None:
    """Latest non-missing value of a column (FRED frames are not forward-filled), or None."""
    if df.empty or col not in df.columns:
        return None
    s = df[col].dropna()
    return float(s.iloc[-1]) if not s.empty else None


if enable_ai:
    payload = build_macro_signal_payload(
        macro_risk_score=float(thermo_series.iloc[-1]) if not thermo_series.empty else None,
        macro_risk_zone=zone_label or None,
        liquidity_yoy=float(liquidity_yoy_series.iloc[-1]) if liquidity_yoy_series is not None and not liquidity_yoy_series.empty else None,
        liquidity_trend="improving" if liquidity_status == "Expanding" else ("contracting" if liquidity_status == "Contracting" else None),
        yield_curve_spread=last_spread_val,
        yield_curve_state=yield_status or None,
        yield_curve_momentum=last_roc_90_val,
        credit_spread=_last(risk_df, "CREDIT_STRESS"),
        credit_stress_state=credit_status or None,
        financial_conditions=fci_status or None,
        spx_regime_zone=zone_label or None,
        btc_price=float(btc_snapshot.get("price")) if btc_snapshot and btc_snapshot.get("price") is not None else None,
        btc_zone=_btc_zone(btc_snapshot) if btc_snapshot else None,
        oil_price=oil_snapshot.get("price"),
        oil_roc_1y=oil_snapshot.get("roc52w"),
        deficit_pct_gdp=_last(fiscal_df, "DEFICIT_PCT_GDP"),
        debt_to_gdp=_last(fiscal_df, "DEBT_PCT_GDP"),
        interest_burden_pct=_last(fiscal_df, "INTEREST_PCT_GDP"),
        readings={sig.label: sig.fmt.format(sig.series.iloc[-1]) for sig in _signals},
        changes=changes_for_prompt(signal_moves),
        changes_since=f"{changes_since:%Y-%m-%d}" if changes_since is not None else None,
    )
    with st.spinner("Generating AI interpretation…"):
        ai_result = generate_ai_summary(payload, macro_drivers_list, date.today().isoformat())

if enable_ai or include_macro_drivers:
    if ai_result and ai_result.get("_error"):
        st.markdown("#### AI Interpretation")
        st.error(f"AI request failed: {ai_result['_error']}")
        st.caption("Charts and raw signals are still current.")
    elif ai_result and "executive_summary" in ai_result:
        st.markdown("#### AI Interpretation")
        with st.container():
            st.markdown("**Executive summary**")
            st.markdown(_md(ai_result.get("executive_summary", "")))
            if ai_result.get("what_changed"):
                st.markdown("**What changed**")
                st.markdown(_md(ai_result.get("what_changed", "")))
            if ai_result.get("what_to_watch"):
                st.markdown("**What to watch**")
                st.markdown(_md(ai_result.get("what_to_watch", "")))
            if ai_result.get("drivers_paragraph"):
                st.markdown(_md(ai_result.get("drivers_paragraph", "")))
            if ai_result.get("chart_insights"):
                st.markdown("**What the charts say about today’s economy**")
                st.markdown(_md(ai_result.get("chart_insights", "")))
            if ai_result.get("asset_implications"):
                st.markdown("**Asset implications**")
                st.markdown(_md(ai_result.get("asset_implications", "")))
        st.divider()
    elif enable_ai and not ai_result:
        st.caption(
            "AI interpretation unavailable. Add **OPENAI_API_KEY** as a root-level key in Settings → Secrets (Streamlit Cloud) or in `.env` / `.streamlit/secrets.toml` (local), save, then **Reboot** the app. Charts and raw signals are still current."
        )
    if macro_drivers_list:
        st.markdown("#### Macro Drivers")
        for a in macro_drivers_list:
            with st.expander(_md(f"{a.get('title', '')} — {a.get('source', '')} ({a.get('date', '')})")):
                st.markdown(_md(a.get("summary", "")))
                if a.get("link"):
                    st.markdown(f"[Read more]({a['link']})")
        st.divider()

# Tab 3 "last" chart: rotation ladder, or FRED-only regime curves when Yahoo is off/unavailable
fig4 = None
last_chart_header = "Rotation Ladder"
last_chart_desc = "Z-score normalized relative strength ratios (risk-on → defensive). Higher line = that ratio outperforming."
if use_fred_only_last_chart or ladder_df.empty:
    regime_curves = prepare_regime_curves(val_df, risk_df)
    fig4 = build_curves_chart(regime_curves, title="Macro Regime (FRED) — 100 = start")
    last_chart_header = "Macro Regime (FRED)"
    last_chart_desc = "FRED-only: S&P 500, Liquidity (WALCL), NFCI, HY spread — rebased to 100 at start."
else:
    fig4 = build_rotation_ladder_chart(ladder_df)


def _build_pdf_summary(ai_summary=None, macro_drivers=None) -> dict:
    """Page-1 section for the PDF: snapshot, Macro Radar, AI interpretation and macro drivers."""
    snapshot = {}
    if macro_score and zone_label:
        snapshot["macro_score"] = macro_score
        snapshot["zone_label"] = zone_label
    if liquidity_status:
        snapshot["liquidity_status"] = liquidity_status
    if yield_status and last_spread_val is not None:
        snapshot["yield_status"] = yield_status
        snapshot["spread_val"] = f"{last_spread_val:.2f}%"
    if credit_status:
        snapshot["credit_status"] = credit_status
    if fci_status:
        snapshot["fci_status"] = fci_status
    return {
        "type": "summary",
        "title": "Executive Summary",
        "report_date": date.today().isoformat(),
        "lookback_label": lookback,
        "data_sources": "FRED, Yahoo Finance",
        "snapshot": snapshot,
        "radar_fig": build_macro_radar_chart(risk_df, liquidity_full, yield_df, thermo_series),
        "ai_summary": ai_summary,
        "macro_drivers": macro_drivers or [],
    }

# ----- Tabs: Macro (Core) | Markets | Regimes & Bands | Fiscal -----
tab_macro, tab_markets, tab_regimes, tab_fiscal = st.tabs(["Macro (Core)", "Markets", "Regimes & Bands", "Fiscal"])

def _col(df: pd.DataFrame, col: str) -> pd.Series | None:
    """A column's observations (frames aren't forward-filled), or None if missing."""
    return df[col].dropna() if not df.empty and col in df.columns else None


def _yoy(series: pd.Series | None) -> pd.Series | None:
    return change_over(series) if series is not None else None


def _card(label: str, series: pd.Series | None, fmt, higher_is_worse: bool, roc: bool = True):
    """Model-input card spec: latest value (formatted by `fmt`), 1Y ROC, and the series for its as-of date."""
    if series is None or series.dropna().empty:
        return None
    s = series.dropna()
    return (label, fmt(s.iloc[-1]), _roc_1y(s) if roc else None, higher_is_worse, s)


def _input_group(title: str, items: list) -> None:
    items = [i for i in items if i is not None]
    if items:
        st.markdown(f"**{title}**")
        _model_input_cards(items)


def _chart_card(title: str, about: str, fig, key: str, png_name: str, missing: str, footer: str = "") -> None:
    """Chart tile for the grid: title, chart (with recession shading), optional footer, PNG export, collapsed description."""
    st.subheader(title)
    if fig is None:
        st.info(missing)
        return
    _plot(fig, key)
    if footer:
        st.caption(footer)
    _png_export(fig, png_name, key)
    with st.expander("About this chart"):
        st.markdown(about)


def _chart_grid(cards: list[dict]) -> None:
    """Two charts per row on wide screens (Streamlit stacks columns on narrow ones)."""
    for i in range(0, len(cards), 2):
        cols = st.columns(2, gap="large")
        for col, card in zip(cols, cards[i:i + 2]):
            with col:
                _chart_card(**card)


with tab_macro:
    st.markdown("#### Model Inputs")
    _pct2 = lambda v: f"{v:.2f}%"
    _pct1 = lambda v: f"{v:.1f}%"
    _mi = model_input_series.get
    _input_group("Rates & inflation", [
        _card("Fed Funds Rate", _col(val_df, "FEDFUNDS"), _pct2, True),
        _card("2Y Treasury", _mi("DGS2"), _pct2, True),
        _card("10Y Treasury", _col(yield_df, "DGS10"), _pct2, True),
        _card("CPI YoY", _yoy(_col(risk_full, "INFLATION")), _pct1, True),
        _card("Core CPI YoY", _yoy(_mi("CPILFESL")), _pct1, True),
        _card("10Y Breakeven", _mi("T10YIE"), _pct2, True),
    ])
    _input_group("Growth & labor", [
        _card("Real GDP YoY", _yoy(_col(risk_full, "GDP")), _pct1, False, roc=False),
        _card("Unemployment", _col(risk_full, "UNEMPLOYMENT"), _pct1, True),
        _card("Sahm Rule", _mi("SAHMREALTIME"), lambda v: f"{v:.2f} pp", True, roc=False),
        _card("Initial Claims", _mi("ICSA"), lambda v: f"{v:,.0f}", True),
    ])
    _input_group("Liquidity & credit", [
        _card("Fed Balance Sheet", _col(liquidity_df, "WALCL"), lambda v: f"${v/1e6:.2f}T", False),  # millions USD
        _card("Net Liquidity", net_liquidity_series, lambda v: f"${v/1e6:.2f}T", False),
        _card("Liquidity YoY", liquidity_yoy_series, _pct1, False, roc=False),
        _card("HY OAS", _col(risk_df, "CREDIT_STRESS"), _pct2, True),
        _card("IG OAS", _mi("BAMLC0A0CM"), _pct2, True),
        _card("NFCI", _col(risk_df, "CREDIT_TIGHTENING"), lambda v: f"{v:.3f}", True),
    ])
    _input_group("Market stress", [
        _card("VIX", _mi("VIXCLS"), lambda v: f"{v:.1f}", True),
        _card("Broad Dollar", _mi("DTWEXBGS"), lambda v: f"{v:.1f}", True),  # strong dollar tightens global conditions
    ])
    st.divider()

    _latest_thermo = thermo_series.iloc[-1] if not thermo_series.empty else None
    _chart_grid([
        dict(
            title="Global Liquidity",
            about="Fed balance sheet (WALCL) year-over-year change. Rising liquidity tends to support asset prices; "
                  "falling liquidity can tighten financial conditions.",
            fig=build_liquidity_chart(liquidity_full, show_event_markers=show_event_markers, display_start=obs_start),
            key="liquidity", png_name="01_global_liquidity.png",
            missing="Not enough liquidity data. Check FRED series WALCL.",
        ),
        dict(
            title="Net Liquidity",
            about="Fed balance sheet minus cash parked at the Treasury (TGA) and in the Fed's overnight reverse repo "
                  "facility — closer to the liquidity actually reaching markets.",
            fig=build_net_liquidity_chart(liquidity_full, show_event_markers=show_event_markers, display_start=obs_start),
            key="net_liquidity", png_name="01b_net_liquidity.png",
            missing="Not enough data for net liquidity. FRED series WALCL, WTREGEN and RRPONTSYD required.",
        ),
        dict(
            title="Stock Market Pressure",
            about="How much pressure the economy is placing on stock prices: `(S&P 500 / unemployment²) × CPI × Fed funds / M2`, "
                  "rebased to 100. Higher values mean more pressure on valuations; lower values tend to support stocks.",
            fig=build_valuation_chart(val_df, overlay_series=overlay_val, show_event_markers=show_event_markers),
            key="vpi", png_name="02_stock_market_pressure.png",
            missing="Not enough valuation data. Check FRED_API_KEY and series availability.",
        ),
        dict(
            title="Economic Risk Index",
            about="Average of six risk pillars, each a 3-year z-score oriented so higher = worse: real GDP growth, "
                  "the 1-year change in unemployment, CPI inflation, financial conditions (NFCI), Fed balance-sheet growth "
                  "and the high-yield spread. The ROC line is the 1-month change — sharp rises often precede market stress.",
            fig=build_macro_risk_chart(risk_df, overlay_series=overlay_risk, show_event_markers=show_event_markers, composite=composite_series),
            key="macro_risk", png_name="03_economic_risk_index.png",
            missing="Not enough macro risk data.",
        ),
        dict(
            title="Yield Curve + Momentum",
            about="10Y – 3M Treasury spread (20-day average, gold) and 10Y – 2Y (green), with 90-day momentum. "
                  "When short rates rise above long rates (inversion, shaded red) it has historically signaled rising recession risk.",
            fig=build_yield_curve_chart(yield_df, show_10y_3m_lines=show_10y_3m_lines, show_event_markers=show_event_markers),
            key="yield", png_name="04_yield_curve_10y_3m.png",
            missing="Not enough yield curve data. Check FRED series DGS10 and DGS3MO.",
        ),
        dict(
            title="Financial Conditions (NFCI)",
            about="Chicago Fed National Financial Conditions Index. Positive = tighter than average (more stress); "
                  "negative = looser (more support for risk assets).",
            fig=build_fci_chart(risk_df, show_ma=True, show_event_markers=show_event_markers),
            key="fci", png_name="05_financial_conditions_index.png",
            missing="Not enough data for Financial Conditions Index. NFCI (FRED) required.",
        ),
        dict(
            title="Credit Spreads",
            about="ICE BofA option-adjusted spreads for high-yield (red) and investment-grade (blue) corporate bonds. "
                  "Rising spreads mean credit is getting more expensive. HY reference lines: 3% calm, 5% stress rising, 7% high stress.",
            fig=build_credit_spreads_chart(risk_df, show_event_markers=show_event_markers, ig_series=_mi("BAMLC0A0CM")),
            key="credit", png_name="06_credit_spreads.png",
            missing="Not enough data for Credit Spreads. BAMLH0A0HYM2 (FRED) required.",
        ),
        dict(
            title="Market Risk Level (0–100)",
            about="1-year percentile of the Economic Risk Index: where today's reading sits relative to the past year. "
                  "Lines mark the zone boundaries (Very Low → Extreme) used across the dashboard.",
            fig=build_thermostat_chart(risk_df, overlay_series=overlay_risk, show_event_markers=show_event_markers, thermo=thermo_series),
            key="thermo", png_name="07_market_risk_level.png",
            missing="Requires macro risk data.",
            footer=f"Current: {_latest_thermo:.0f}/100 — {risk_zone(_latest_thermo)}" if _latest_thermo is not None else "",
        ),
    ])

with tab_markets:
    st.markdown("#### Model Inputs")
    _sp500 = val_df["SP500"].dropna() if not val_df.empty and "SP500" in val_df.columns else pd.Series(dtype=float)
    _wti = oil_df["DCOILWTICO"].dropna() if not oil_df.empty and "DCOILWTICO" in oil_df.columns else pd.Series(dtype=float)
    _market_inputs = []
    if btc_snapshot and btc_snapshot.get("price") is not None:
        _market_inputs.append(("Bitcoin Price", f"${btc_snapshot['price']:,.0f}", btc_snapshot.get("roc52w"), False))
    for ma in ["wma50", "wma100", "wma200", "wma300"]:
        if btc_snapshot and btc_snapshot.get(ma) is not None:
            _market_inputs.append((f"BTC {ma.upper()}", f"${btc_snapshot[ma]:,.0f}", None, False))
    if not _sp500.empty:
        _market_inputs.append(("S&P 500", f"{_sp500.iloc[-1]:,.0f}", _roc_1y(_sp500), False))
    if not _wti.empty:
        _market_inputs.append(("WTI Oil", f"${_wti.iloc[-1]:.2f}", _roc_1y(_wti), False))
    _model_input_cards(_market_inputs)
    st.markdown("#### Today's Snapshot")
    # BTC strip
    if btc_snapshot and btc_snapshot.get("price") is not None:
        st.caption("**BTC**")
        r1, r2, r3, r4, r5 = st.columns(5)
        with r1:
            st.metric("BTC Price", f"${btc_snapshot['price']:,.0f}" if btc_snapshot.get("price") else "—")
            for k in ["wma50", "wma100", "wma200", "wma300"]:
                v = btc_snapshot.get(k)
                st.caption(f"{k}: ${v:,.0f}" if v is not None else f"{k}: —")
        with r2:
            st.metric("Balanced (proxy)", f"${btc_snapshot['balanced_price']:,.0f}" if btc_snapshot.get("balanced_price") else "—")
            st.metric("Terminal (proxy)", f"${btc_snapshot['terminal_price']:,.0f}" if btc_snapshot.get("terminal_price") else "—")
        with r3:
            for label, key in [("1W", "roc1w"), ("4W", "roc4w"), ("12W", "roc12w"), ("52W", "roc52w")]:
                v = btc_snapshot.get(key)
                st.metric(f"ROC {label}", f"{v:.1f}%" if v is not None else "—")
        with r4:
            v200 = btc_snapshot.get("dist_200wma_pct")
            v300 = btc_snapshot.get("dist_300wma_pct")
            st.metric("Dist 200WMA", f"{v200:.1f}%" if v200 is not None else "—")
            st.metric("Dist 300WMA", f"{v300:.1f}%" if v300 is not None else "—")
        with r5:
            st.caption("WMAs = weighted moving avg (weekly)")
    # Oil snapshot
    if oil_snapshot:
        st.caption("**Oil (WTI)**")
        o1, o2, o3 = st.columns(3)
        with o1:
            st.metric("WTI Spot", f"${oil_snapshot.get('price', 0):.2f}" if oil_snapshot.get("price") is not None else "—")
        with o2:
            v = oil_snapshot.get("roc4w")
            st.metric("4W ROC", f"{v:.1f}%" if v is not None else "—")
        with o3:
            v = oil_snapshot.get("roc52w")
            st.metric("52W ROC", f"{v:.1f}%" if v is not None else "—")
    st.divider()

    st.header("Oil (WTI)")
    st.markdown(
        '<p class="section-desc">WTI spot price (FRED DCOILWTICO). Use toggles for log scale, YoY % change, and CPI YoY overlay.</p>',
        unsafe_allow_html=True,
    )
    fig_oil = build_oil_chart(
        oil_df,
        log_scale=oil_log_scale,
        show_yoy=oil_show_yoy,
        cpi_series=cpi_series if oil_show_cpi else None,
        show_event_markers=show_event_markers,
    )
    if fig_oil is not None:
        _plot(fig_oil, "oil")
    else:
        st.info("Not enough oil data. Check FRED DCOILWTICO and API key.")

    st.header("Bitcoin (BTC/USD)")
    st.markdown(
        '<p class="section-desc">Bitcoin price from FRED (CBBTCUSD) or Yahoo Finance. Overlays: Liquidity YoY (WALCL), 10Y TIPS real yield.</p>',
        unsafe_allow_html=True,
    )
    fig_btc = build_bitcoin_chart(
        btc_display,
        log_scale=btc_log_scale,
        liquidity_yoy_series=liquidity_yoy_series if btc_show_liquidity else None,
        real_yield_series=real_yield_series if btc_show_real_yield else None,
        show_event_markers=show_event_markers,
    )
    if fig_btc is not None:
        _plot(fig_btc, "btc")
    else:
        st.info("Not enough Bitcoin data. Try FRED CBBTCUSD or Yahoo BTC-USD.")

    st.header("Bitcoin Rainbow (Log Regression Bands)")
    st.markdown(
        '<p class="section-desc">Log regression bands (full history); display follows lookback. Balanced = midline; Terminal = lower band (proxy).</p>',
        unsafe_allow_html=True,
    )
    fig_rainbow = build_btc_rainbow_chart(
        btc_series,
        display_start=obs_start,
        log_scale=btc_log_scale,
    )
    if fig_rainbow is not None:
        _plot(fig_rainbow, "btc_rainbow")
    else:
        st.info("Not enough BTC history for Rainbow (need 30+ points).")

with tab_regimes:
    st.markdown("#### Model Inputs")
    _spread_series = yield_df["DGS10"].sub(yield_df["DGS3MO"]).dropna() if not yield_df.empty and "DGS10" in yield_df.columns and "DGS3MO" in yield_df.columns else pd.Series(dtype=float)
    _regime_inputs = []
    if not thermo_series.empty:
        _regime_inputs.append(("Market Risk Score", f"{thermo_series.iloc[-1]:.0f}/100", _roc_1y(thermo_series), True))
    if liquidity_yoy_series is not None and not liquidity_yoy_series.empty:
        _regime_inputs.append(("Liquidity YoY", f"{liquidity_yoy_series.iloc[-1]:.1f}%", _roc_1y(liquidity_yoy_series), False))
    if not _spread_series.empty:
        _regime_inputs.append(("Yield Curve (10Y–3M)", f"{_spread_series.iloc[-1]:.2f}%", _roc_1y(_spread_series), False))  # higher spread = steeper = better
    if not risk_df.empty and "CREDIT_STRESS" in risk_df.columns:
        _hy = risk_df["CREDIT_STRESS"].dropna()
        if not _hy.empty:
            _regime_inputs.append(("Credit Spread", f"{_hy.iloc[-1]:.2f}%", _roc_1y(_hy), True))
    if not risk_df.empty and "CREDIT_TIGHTENING" in risk_df.columns:
        _n = risk_df["CREDIT_TIGHTENING"].dropna()
        if not _n.empty:
            _regime_inputs.append(("NFCI", f"{_n.iloc[-1]:.3f}", _roc_1y(_n), True))
    _model_input_cards(_regime_inputs)
    st.markdown("#### Today's Snapshot")
    r1, r2, r3, r4, r5 = st.columns(5)
    with r1:
        risk_val = thermo_series.iloc[-1] if not thermo_series.empty else None
        zone = risk_zone(risk_val) if risk_val is not None else "—"
        _metric_note("Risk score", f"{risk_val:.0f}/100" if risk_val is not None else "—", zone)
    with r2:
        liq_yoy = None
        if liquidity_yoy_series is not None and not liquidity_yoy_series.empty:
            liq_yoy = float(liquidity_yoy_series.iloc[-1])
        _metric_note("Liquidity YoY", f"{liq_yoy:.1f}%" if liq_yoy is not None else "—", "WALCL")
    with r3:
        spread_str = f"{last_spread_val:.2f}%" if last_spread_val is not None else "—"
        mom_str = f"{last_roc_90_val:.2f}" if last_roc_90_val is not None else "—"
        _metric_note("Yield curve (10Y–3M)", spread_str, yield_status or "")
        st.caption(f"Momentum (90d): {mom_str}")
    with r4:
        hy = None
        if not risk_df.empty and "CREDIT_STRESS" in risk_df.columns:
            s = risk_df["CREDIT_STRESS"].dropna()
            hy = float(s.iloc[-1]) if len(s) else None
        st.metric("HY OAS", f"{hy:.2f}%" if hy is not None else "—")
    with r5:
        nfci = None
        if not risk_df.empty and "CREDIT_TIGHTENING" in risk_df.columns:
            s = risk_df["CREDIT_TIGHTENING"].dropna()
            nfci = float(s.iloc[-1]) if len(s) else None
        _metric_note("NFCI", f"{nfci:.3f}" if nfci is not None else "—", "FCI")
    st.divider()
    st.markdown(
        "**Macro Risk Bands** use the Market Risk Level (0–100) to shade each chart by regime. "
        "Green/blue = lower risk (opportunity); yellow/orange/red = higher risk (caution)."
    )
    sp500_series = val_df["SP500"].dropna() if not val_df.empty and "SP500" in val_df.columns else pd.Series(dtype=float)
    if not sp500_series.empty and not thermo_series.empty:
        st.subheader("S&P 500 with risk bands")
        st.caption("Background color shows macro risk zone over time. Price (white line) on top.")
        fig_bands_spx = build_bands_chart(sp500_series, thermo_series, "S&P 500 — Macro Risk Bands", show_event_markers=show_event_markers, log_scale=spx_log_scale)
        if fig_bands_spx is not None:
            _plot(fig_bands_spx, "bands_spx", shade_recessions=False)
    else:
        st.info("Need valuation and risk data for S&P 500 bands.")

    if not btc_display.empty and not thermo_series.empty:
        st.subheader("Bitcoin with risk bands")
        st.caption("BTC price with same macro risk zone shading.")
        fig_bands_btc = build_bands_chart(btc_display, thermo_series, "Bitcoin — Macro Risk Bands", show_event_markers=show_event_markers)
        if fig_bands_btc is not None:
            _plot(fig_bands_btc, "bands_btc", shade_recessions=False)
    else:
        st.info("Need Bitcoin and risk data for bands.")

    oil_price_series = oil_df["DCOILWTICO"].dropna() if not oil_df.empty and "DCOILWTICO" in oil_df.columns else pd.Series(dtype=float)
    if not oil_price_series.empty and not thermo_series.empty:
        st.subheader("Oil (WTI) with risk bands")
        st.caption("Oil price with macro risk zone shading.")
        fig_bands_oil = build_bands_chart(oil_price_series, thermo_series, "WTI Oil — Macro Risk Bands", show_event_markers=show_event_markers)
        if fig_bands_oil is not None:
            _plot(fig_bands_oil, "bands_oil", shade_recessions=False)
    else:
        st.info("Need oil and risk data for bands.")

    st.subheader(last_chart_header)
    st.markdown(f'<p class="section-desc">{last_chart_desc}</p>', unsafe_allow_html=True)
    if fig4 is not None:
        _plot(fig4, "rotation")
        _png_export(fig4, "08_rotation_ladder.png", "rot")
    else:
        st.info("Chart data could not be loaded. Try \"Use FRED-only for final chart\" if Yahoo fails.")

with tab_fiscal:
    st.markdown("#### Model Inputs")
    _def_pct = fiscal_df["DEFICIT_PCT_GDP"].dropna() if not fiscal_df.empty and "DEFICIT_PCT_GDP" in fiscal_df.columns else pd.Series(dtype=float)
    _debt_pct = fiscal_df["DEBT_PCT_GDP"].dropna() if not fiscal_df.empty and "DEBT_PCT_GDP" in fiscal_df.columns else pd.Series(dtype=float)
    _net_int = fiscal_df["NET_INTEREST"].dropna() if not fiscal_df.empty and "NET_INTEREST" in fiscal_df.columns else pd.Series(dtype=float)
    _int_pct = fiscal_df["INTEREST_PCT_GDP"].dropna() if not fiscal_df.empty and "INTEREST_PCT_GDP" in fiscal_df.columns else pd.Series(dtype=float)
    _fiscal_inputs = []
    if not _def_pct.empty:
        _fiscal_inputs.append(("Annual Deficit % GDP", f"{_def_pct.iloc[-1]:.2f}%", _roc_1y(_def_pct), True, _def_pct))  # annual
    if not _debt_pct.empty:
        _fiscal_inputs.append(("Debt-to-GDP", f"{_debt_pct.iloc[-1]:.1f}%", _roc_1y(_debt_pct), True, _debt_pct))  # annual
    if not _net_int.empty:
        _fiscal_inputs.append(("Net Interest ($B)", f"{_net_int.iloc[-1]:.1f}", _roc_1y(_net_int), True, _net_int))  # quarterly
    if not _int_pct.empty:
        _fiscal_inputs.append(("Interest % GDP", f"{_int_pct.iloc[-1]:.2f}%", _roc_1y(_int_pct), True, _int_pct))  # quarterly
    _model_input_cards(_fiscal_inputs)
    st.divider()

    _chart_grid([
        dict(
            title="Annual Deficit (% of GDP)",
            about="How much the federal government spends beyond its income, relative to the size of the economy. "
                  "Higher values mean larger fiscal imbalances.",
            fig=build_deficit_pct_gdp_chart(fiscal_df, show_event_markers=show_event_markers),
            key="fiscal_deficit", png_name="fiscal_deficit_pct_gdp.png",
            missing="Not enough fiscal data. Check FRED series FYFSGDA188S (Surplus/Deficit as % GDP).",
        ),
        dict(
            title="Federal Debt-to-GDP",
            about="The national debt relative to the economy. Rising levels suggest the debt burden is getting harder to manage.",
            fig=build_debt_to_gdp_chart(fiscal_df, show_event_markers=show_event_markers),
            key="fiscal_debt", png_name="fiscal_debt_to_gdp.png",
            missing="Not enough fiscal data. Check FRED series FYGFDPUN (Debt % GDP).",
        ),
        dict(
            title="Net Interest Burden (% of GDP)",
            about="Federal net interest outlays as a share of GDP. Rising values reduce fiscal flexibility and raise long-term risk.",
            fig=build_interest_burden_chart(fiscal_df, show_event_markers=show_event_markers),
            key="fiscal_interest", png_name="fiscal_interest_burden.png",
            missing="Not enough fiscal data. Check FRED series B091RC1Q027SBEA (Net interest) and GDP.",
        ),
    ])

# ----- Generate PDF (Executive Summary + Macro Radar) -----
if pdf_available() and build_dashboard_pdf:
    def _pdf_export_fn(fig):
        if fig is None:
            return None
        png, _ = _png_from_json(_fig_for_pdf(fig).to_json())
        return png

    try:
        # PDF = summary only (no chart images), so it always works with zero setup
        summary = _build_pdf_summary(
            ai_summary=(ai_result if (enable_ai and ai_result and not ai_result.get("_error")) else None),
            macro_drivers=macro_drivers_list if include_macro_drivers else [],
        )
        pdf_bytes = build_dashboard_pdf(
            [summary],
            report_date=date.today().isoformat(),
            lookback_label=lookback,
            data_sources="FRED, Yahoo Finance",
            export_fn=_pdf_export_fn,
        )
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="macro_intelligence_brief.pdf",
            mime="application/pdf",
            key="dl_pdf",
        )
        st.caption("Summary only. View all charts in the dashboard above.")
    except Exception as e:
        st.caption(f"PDF could not be generated: {e}")

st.markdown("""
<div class="footer">
    Private Macro Dashboard · <a href="https://github.com/CtrlAltDelegate/macro-dashboard" target="_blank" rel="noopener">GitHub</a> · 
    FRED + Yahoo Finance · Export PNG for newsletter
</div>
""", unsafe_allow_html=True)
