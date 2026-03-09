"""
Macro Dashboard — Private, local-first. Run: streamlit run app.py
"""
from __future__ import annotations

import io
import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from dotenv import load_dotenv

load_dotenv()
import streamlit as st

# Streamlit Cloud: secrets in st.secrets; put FRED_API_KEY and OPENAI_API_KEY into env
try:
    if hasattr(st, "secrets"):
        val = getattr(st.secrets, "get", lambda k: None)("FRED_API_KEY") or getattr(st.secrets, "FRED_API_KEY", None)
        if not val and "FRED_API_KEY" in st.secrets:
            val = st.secrets["FRED_API_KEY"]
        if val:
            os.environ.setdefault("FRED_API_KEY", str(val))
        ak = getattr(st.secrets, "OPENAI_API_KEY", None)
        if not ak and "OPENAI_API_KEY" in st.secrets:
            ak = st.secrets["OPENAI_API_KEY"]
        if not ak and hasattr(st.secrets, "openai"):
            ak = getattr(st.secrets.openai, "OPENAI_API_KEY", None)
        if ak:
            os.environ.setdefault("OPENAI_API_KEY", str(ak))
except Exception:
    pass

import config

# Server-side log: appears in Streamlit Cloud "Manage app" → Logs (not in browser console)
print(f"[Macro Dashboard] FRED_API_KEY set: {bool(config.FRED_API_KEY)}, OPENAI_API_KEY set: {bool(config.OPENAI_API_KEY)}")

from charts.build import (
    build_valuation_chart,
    build_macro_risk_chart,
    build_yield_curve_chart,
    build_liquidity_chart,
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
)
from data import (
    fetch_valuation_data,
    fetch_macro_risk_data,
    fetch_yield_curve_data,
    fetch_liquidity_data,
    fetch_rotation_data,
    fetch_oil_data,
    fetch_bitcoin_data,
    fetch_real_yield_data,
    fetch_fiscal_data,
    fetch_model_input_series,
)
from data.market_data import fetch_rotation_ladder_data
from models import compute_macro_risk_composite, compute_risk_thermostat, prepare_regime_curves
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
    from ai_summary import build_macro_signal_payload, generate_ai_summary, ai_summary_available
except ImportError:
    build_macro_signal_payload = lambda **k: {}
    generate_ai_summary = lambda *a, **k: None
    ai_summary_available = lambda: False

try:
    from plotly_export import export_plotly_to_png_or_error
except ImportError:
    def export_plotly_to_png_or_error(fig, *, width=800, height=450):
        return None, "plotly_export not available"


def _try_export_png(fig):
    """Export Plotly figure to PNG via Playwright (no Kaleido). Returns (bytes, None) or (None, error_msg)."""
    return export_plotly_to_png_or_error(fig, width=800, height=450)


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
    .stApp { max-width: 1100px; margin: 0 auto; padding: 0 1rem 2rem; }
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


def _roc_1y(series: pd.Series, periods: int) -> float | None:
    """1-year rate of change in percent. periods: 12=monthly, 52=weekly, 252=daily."""
    if series is None or series.empty or len(series) < periods + 1:
        return None
    old = series.iloc[-periods - 1]
    new = series.iloc[-1]
    if old == 0 or not pd.notna(old) or not pd.notna(new):
        return None
    return ((new - old) / abs(old)) * 100


def _model_input_cards(
    items: list[tuple[str, str, float | None, bool]],
) -> None:
    """Render a row of model input cards. Each item: (label, value_str, roc_1y or None, higher_is_worse)."""
    if not items:
        return
    n = len(items)
    cols = st.columns(min(n, 6) if n > 4 else n)
    for i, (label, value_str, roc, higher_is_worse) in enumerate(items):
        with cols[i % len(cols)]:
            delta_str = f"1Y ROC {roc:+.1f}%" if roc is not None else None
            delta_color = "inverse" if higher_is_worse else "normal"  # inverse: positive ROC = red
            st.metric(label, value_str, delta=delta_str, delta_color=delta_color if delta_str else "off")

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
        value=bool(getattr(config, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")),
        help="Show AI-generated executive summary and interpretation. Requires OPENAI_API_KEY.",
    )
    include_macro_drivers = st.checkbox("Include Macro Drivers headlines", value=True, help="Show 3–5 recent macro-relevant headlines.")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

@st.cache_data(ttl=3600)
def load_all(lookback: str):
    obs_start = config.lookback_to_observation_start(lookback)
    rot_period = config.lookback_to_rotation_period(lookback)
    val_df = fetch_valuation_data(observation_start=obs_start)
    risk_df = fetch_macro_risk_data(observation_start=obs_start)
    yield_df = fetch_yield_curve_data(observation_start=obs_start)
    liquidity_df = fetch_liquidity_data(observation_start=obs_start)
    try:
        rot_df = fetch_rotation_data(period=rot_period)
    except Exception:
        rot_df = pd.DataFrame()
    oil_df = pd.DataFrame()
    btc_series = pd.Series(dtype=float)
    real_yield_series = pd.Series(dtype=float)
    if config.FRED_API_KEY:
        try:
            oil_df = fetch_oil_data(observation_start=obs_start)
        except Exception:
            pass
        try:
            btc_series = fetch_bitcoin_data(observation_start=obs_start, yfinance_period=rot_period)
        except Exception:
            pass
        try:
            real_yield_series = fetch_real_yield_data(observation_start=obs_start)
        except Exception:
            pass
    try:
        ladder_df = fetch_rotation_ladder_data(period=rot_period)
    except Exception:
        ladder_df = pd.DataFrame()
    fiscal_df = pd.DataFrame()
    model_input_series = {}
    if config.FRED_API_KEY:
        try:
            fiscal_df = fetch_fiscal_data(observation_start=obs_start)
        except Exception:
            pass
        try:
            model_input_series = fetch_model_input_series(observation_start=obs_start)
        except Exception:
            pass
    return val_df, risk_df, yield_df, liquidity_df, rot_df, oil_df, btc_series, real_yield_series, ladder_df, fiscal_df, model_input_series

try:
    val_df, risk_df, yield_df, liquidity_df, rot_df, oil_df, btc_series, real_yield_series, ladder_df, fiscal_df, model_input_series = load_all(lookback)
except Exception as e:
    st.error(f"Data load failed: {e}")
    val_df = risk_df = yield_df = liquidity_df = rot_df = oil_df = fiscal_df = pd.DataFrame()
    btc_series = real_yield_series = pd.Series(dtype=float)
    ladder_df = pd.DataFrame()
    model_input_series = {}

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

# Thermo (0-100) for Regimes bands and readout
thermo_series = pd.Series(dtype=float)
if not risk_df.empty:
    raw = compute_macro_risk_composite(risk_df)
    thermo_series = compute_risk_thermostat(raw)
# Liquidity YoY for BTC overlay (WALCL is weekly)
liquidity_yoy_series = None
if not liquidity_df.empty and "WALCL" in liquidity_df.columns and len(liquidity_df["WALCL"]) >= 53:
    walcl = liquidity_df["WALCL"].dropna()
    liquidity_yoy_series = ((walcl / walcl.shift(52)) - 1) * 100
    liquidity_yoy_series = liquidity_yoy_series.dropna()
# CPI for oil overlay (from macro risk INFLATION = CPIAUCSL)
cpi_series = risk_df["INFLATION"].dropna() if not risk_df.empty and "INFLATION" in risk_df.columns else None
# BTC snapshot (WMAs, ROC, distances, Balanced/Terminal); terminal_k from sidebar
btc_snapshot = compute_btc_snapshot(btc_series, terminal_k=btc_rainbow_k) if btc_series is not None and not btc_series.empty else {}
# Oil snapshot (current WTI, 4W ROC, 52W ROC)
oil_snapshot = {}
if not oil_df.empty and "DCOILWTICO" in oil_df.columns:
    oil_price = oil_df["DCOILWTICO"].dropna()
    if len(oil_price) >= 2:
        oil_snapshot["price"] = float(oil_price.iloc[-1])
        if len(oil_price) > 28:
            oil_snapshot["roc4w"] = (oil_price.iloc[-1] / oil_price.iloc[-28] - 1) * 100
        if len(oil_price) >= 253:
            oil_snapshot["roc52w"] = (oil_price.iloc[-1] / oil_price.iloc[-252] - 1) * 100


def _thermo_zone(value: float) -> str:
    if value < 20:
        return "Very Low Risk"
    if value < 40:
        return "Low Risk"
    if value < 60:
        return "Moderate Risk"
    if value < 80:
        return "High Risk"
    return "Extreme Risk"


def _regime_zone_label_6(value: float) -> str:
    """Six zones for Regimes tab snapshot (0–20, 20–40, 40–60, 60–75, 75–90, 90–100)."""
    if value < 20:
        return "Very Low Risk"
    if value < 40:
        return "Low Risk"
    if value < 60:
        return "Moderate Risk"
    if value < 75:
        return "High Risk"
    if value < 90:
        return "Very High Risk"
    return "Extreme Risk"


def _regime_tendency_text(zone: str) -> str:
    """Short factual text for current zone (neutral language)."""
    m = {
        "Very Low Risk": "Historically, this zone has tended to favor risk-on assets.",
        "Low Risk": "Historically, this zone has often supported equities and risk assets.",
        "Moderate Risk": "Historically, this zone has been mixed; diversification often helps.",
        "High Risk": "Historically, this zone has often favored more defensive positioning.",
        "Very High Risk": "Historically, this zone has often favored capital preservation.",
        "Extreme Risk": "Historically, this zone has often favored defensive assets and cash.",
    }
    return m.get(zone, "Zone-dependent; consider macro context.")


# ----- Current Readout Panel -----
def _readout_chip(label: str, value: str, style: str = "neutral") -> str:
    return f'<span class="readout-chip readout-chip--{style}"><span class="readout-label">{label}</span>{value}</span>'


macro_score = ""
zone_label = ""
liquidity_status = ""
yield_status = ""
yield_mom_status = ""
fci_status = ""
credit_status = ""

if not risk_df.empty:
    raw = compute_macro_risk_composite(risk_df)
    thermo = compute_risk_thermostat(raw)
    if not thermo.empty:
        latest_thermo = thermo.iloc[-1]
        macro_score = f"{latest_thermo:.0f}/100"
        zone_label = _thermo_zone(latest_thermo)

if not liquidity_df.empty and "WALCL" in liquidity_df.columns:
    walcl = liquidity_df["WALCL"].dropna()
    if len(walcl) >= 53:
        yoy = ((walcl / walcl.shift(52)) - 1) * 100
        yoy = yoy.dropna()
        if not yoy.empty:
            last_yoy = yoy.iloc[-1]
            liquidity_status = "Expanding" if last_yoy >= 0 else "Contracting"

last_spread_val = None
last_roc_90_val = None
if not yield_df.empty and "DGS10" in yield_df.columns and "DGS3MO" in yield_df.columns:
    spread = yield_df["DGS10"].sub(yield_df["DGS3MO"]).dropna()
    if not spread.empty:
        last_spread_val = spread.iloc[-1]
        yield_status = "Inverted" if last_spread_val < 0 else "Normal"
        if len(spread) >= 91:
            last_roc_90_val = spread.iloc[-1] - spread.iloc[-91]
            yield_mom_status = "Steepening" if last_roc_90_val > 0 else "Falling"

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
if yield_mom_status and last_roc_90_val is not None:
    chips.append(_readout_chip("YC Momentum", f"{last_roc_90_val:.2f} ({yield_mom_status})", "green" if yield_mom_status == "Steepening" else "yellow"))
if fci_status:
    chips.append(_readout_chip("Financial Conditions", fci_status, "red" if fci_status == "Tight" else "green"))
if credit_status:
    chip_style = "red" if credit_status == "High" else "yellow" if credit_status == "Moderate" else "green"
    chips.append(_readout_chip("Credit Stress", credit_status, chip_style))

if chips:
    st.markdown('<div class="readout-panel">' + "".join(chips) + "</div>", unsafe_allow_html=True)

# ----- AI Interpretation + Macro Drivers -----
ai_result = None
macro_drivers_list = []
if include_macro_drivers:
    with st.spinner("Fetching macro headlines…"):
        _news = fetch_recent_macro_news(max_articles=12, max_age_days=7)
        macro_drivers_list = rank_macro_relevance(_news, max_return=5)

# Sync OpenAI key from Streamlit secrets at runtime (Cloud often has secrets only per-request)
def _ensure_openai_key():
    if os.getenv("OPENAI_API_KEY"):
        return
    try:
        if hasattr(st, "secrets"):
            ak = getattr(st.secrets, "OPENAI_API_KEY", None)
            if not ak and "OPENAI_API_KEY" in st.secrets:
                ak = st.secrets["OPENAI_API_KEY"]
            if not ak and hasattr(st.secrets, "openai"):
                ak = getattr(st.secrets.openai, "OPENAI_API_KEY", None)
            if ak:
                os.environ["OPENAI_API_KEY"] = str(ak)
    except Exception:
        pass

if enable_ai:
    _ensure_openai_key()
    payload = build_macro_signal_payload(
        macro_risk_score=float(thermo_series.iloc[-1]) if not thermo_series.empty else None,
        macro_risk_zone=zone_label or None,
        liquidity_yoy=float(liquidity_yoy_series.iloc[-1]) if liquidity_yoy_series is not None and not liquidity_yoy_series.empty else None,
        liquidity_trend="improving" if liquidity_status == "Expanding" else ("contracting" if liquidity_status == "Contracting" else None),
        yield_curve_spread=last_spread_val,
        yield_curve_state=yield_status or None,
        yield_curve_momentum=last_roc_90_val,
        credit_spread=float(risk_df["CREDIT_STRESS"].iloc[-1]) if not risk_df.empty and "CREDIT_STRESS" in risk_df.columns and len(risk_df["CREDIT_STRESS"].dropna()) else None,
        credit_stress_state=credit_status or None,
        financial_conditions=fci_status or None,
        spx_regime_zone=zone_label or None,
        btc_price=float(btc_snapshot.get("price")) if btc_snapshot and btc_snapshot.get("price") is not None else None,
        btc_zone="mid-band",
        oil_price=float(oil_snapshot.get("price")) if oil_snapshot and oil_snapshot.get("price") is not None else None,
        oil_roc_1y=float(oil_snapshot.get("roc52w")) if oil_snapshot and oil_snapshot.get("roc52w") is not None else None,
        deficit_pct_gdp=float(fiscal_df["DEFICIT_PCT_GDP"].iloc[-1]) if not fiscal_df.empty and "DEFICIT_PCT_GDP" in fiscal_df.columns and not fiscal_df["DEFICIT_PCT_GDP"].dropna().empty else None,
        debt_to_gdp=float(fiscal_df["DEBT_PCT_GDP"].iloc[-1]) if not fiscal_df.empty and "DEBT_PCT_GDP" in fiscal_df.columns and not fiscal_df["DEBT_PCT_GDP"].dropna().empty else None,
        interest_burden_pct=float(fiscal_df["INTEREST_PCT_GDP"].iloc[-1]) if not fiscal_df.empty and "INTEREST_PCT_GDP" in fiscal_df.columns and not fiscal_df["INTEREST_PCT_GDP"].dropna().empty else None,
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
            st.markdown(ai_result.get("executive_summary", ""))
            if ai_result.get("what_changed"):
                st.markdown("**What changed**")
                st.markdown(ai_result.get("what_changed", ""))
            if ai_result.get("what_to_watch"):
                st.markdown("**What to watch**")
                st.markdown(ai_result.get("what_to_watch", ""))
            if ai_result.get("drivers_paragraph"):
                st.markdown(ai_result.get("drivers_paragraph", ""))
            if ai_result.get("chart_insights"):
                st.markdown("**What the charts say about today’s economy**")
                st.markdown(ai_result.get("chart_insights", ""))
            if ai_result.get("asset_implications"):
                st.markdown("**Asset implications**")
                st.markdown(ai_result.get("asset_implications", ""))
        st.divider()
    elif enable_ai and not ai_result:
        st.caption(
            "AI interpretation unavailable. Add **OPENAI_API_KEY** as a root-level key in Settings → Secrets (Streamlit Cloud) or in `.env` / `.streamlit/secrets.toml` (local), save, then **Reboot** the app. Charts and raw signals are still current."
        )
    if macro_drivers_list:
        st.markdown("#### Macro Drivers")
        for a in macro_drivers_list:
            with st.expander(f"{a.get('title', '')} — {a.get('source', '')} ({a.get('date', '')})"):
                st.markdown(a.get("summary", ""))
                if a.get("link"):
                    st.markdown(f"[Read more]({a['link']})")
        st.divider()

# Build Tab 3 "last" chart once for PDF (rotation ladder or FRED regime)
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


def _build_pdf_sections(
    lookback,
    show_event_markers,
    show_10y_3m_lines,
    show_market_overlay,
    oil_log_scale,
    oil_show_yoy,
    oil_show_cpi,
    btc_log_scale,
    btc_show_liquidity,
    btc_show_real_yield,
    btc_rainbow_k,
    spx_log_scale,
    use_fred_only_last_chart,
    val_df,
    risk_df,
    yield_df,
    liquidity_df,
    rot_df,
    oil_df,
    btc_series,
    real_yield_series,
    ladder_df,
    overlay_val,
    overlay_risk,
    thermo_series,
    liquidity_yoy_series,
    cpi_series,
    ai_summary=None,
    macro_drivers=None,
):
    """Build full report sections: Executive Summary + Macro Radar + AI/Drivers, then all charts."""
    obs_start = config.lookback_to_observation_start(lookback)
    sections = []

    # Snapshot for Page 1
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

    # Radar figure (recomputed for PDF)
    radar_fig = build_macro_radar_chart(risk_df, liquidity_df, yield_df, thermo_series)

    summary_section = {
        "type": "summary",
        "title": "Executive Summary",
        "report_date": date.today().isoformat(),
        "lookback_label": lookback,
        "data_sources": "FRED, Yahoo Finance",
        "snapshot": snapshot,
        "radar_fig": radar_fig,
        "ai_summary": ai_summary,
        "macro_drivers": macro_drivers or [],
    }
    sections.append(summary_section)

    # Macro (Core) tab charts — same figures already built above
    macro_captions = [
        "Global liquidity (Fed balance sheet YoY). Rising liquidity tends to support asset prices; falling liquidity can tighten financial conditions.",
        "Stock market pressure combines rates, inflation, unemployment, and liquidity. Higher values mean more pressure on valuations; lower values tend to support stocks.",
        "Economic risk index combines multiple macro indicators. The blue line shows current risk level; the ROC line shows how quickly conditions are changing.",
        "Yield curve (10Y – 3M). An inverted curve has historically signaled increasing recession risk.",
        "Chicago Fed NFCI. Higher values indicate tighter financial conditions; lower values indicate easier conditions. Zero is the baseline.",
        "ICE BofA US High Yield OAS. Rising spreads mean credit stress is increasing. Reference: 3% calm, 5% stress rising, 7% high stress.",
        "Market risk level (0–100) from macro signals. Lower scores suggest a stable environment; higher scores suggest growing stress. Bands indicate very low through extreme risk.",
    ]
    macro_tuples = [
        ("Global Liquidity", macro_captions[0], fig_liquidity),
        ("Stock Market Pressure", macro_captions[1], fig1),
        ("Economic Risk Index", macro_captions[2], fig2),
        ("Yield Curve (10Y – 3M) + Momentum", macro_captions[3], fig_yield),
        ("Financial Conditions Index", macro_captions[4], fig_fci),
        ("Credit Spreads (High Yield OAS)", macro_captions[5], fig_credit),
        ("Market Risk Level (0–100)", macro_captions[6], fig3),
    ]
    for title, caption, fig in macro_tuples:
        if fig is not None:
            sections.append({"type": "chart", "title": f"Macro — {title}", "caption": caption, "fig": fig})

    # Markets tab charts — build here for PDF (recompute so PDF does not depend on active tab)
    fig_oil = build_oil_chart(
        oil_df,
        log_scale=oil_log_scale,
        show_yoy=oil_show_yoy,
        cpi_yoy_series=cpi_series,
        show_event_markers=show_event_markers,
    )
    fig_btc = build_bitcoin_chart(
        btc_series,
        log_scale=btc_log_scale,
        liquidity_yoy_series=liquidity_yoy_series if btc_show_liquidity else None,
        real_yield_series=real_yield_series if btc_show_real_yield else None,
        show_event_markers=show_event_markers,
    )
    fig_rainbow = build_btc_rainbow_chart(btc_series, display_start=obs_start, log_scale=btc_log_scale)
    if fig_oil is not None:
        sections.append({
            "type": "chart",
            "title": "Markets — Oil (WTI)",
            "caption": "WTI spot price (FRED DCOILWTICO). Reflects commodity and inflation expectations.",
            "fig": fig_oil,
        })
    if fig_btc is not None:
        sections.append({
            "type": "chart",
            "title": "Markets — Bitcoin (BTC/USD)",
            "caption": "Bitcoin price from FRED or Yahoo Finance. Optional overlays: Liquidity YoY, 10Y TIPS real yield.",
            "fig": fig_btc,
        })
    if fig_rainbow is not None:
        sections.append({
            "type": "chart",
            "title": "Markets — Bitcoin Rainbow (Log Regression Bands)",
            "caption": "Log regression bands (full history). Balanced = midline; Terminal = lower band proxy.",
            "fig": fig_rainbow,
        })

    # Regimes & Bands tab charts
    sp500_series = val_df["SP500"].dropna() if not val_df.empty and "SP500" in val_df.columns else pd.Series(dtype=float)
    oil_price_series = oil_df["DCOILWTICO"].dropna() if not oil_df.empty and "DCOILWTICO" in oil_df.columns else pd.Series(dtype=float)
    if not sp500_series.empty and not thermo_series.empty:
        fig_bands_spx = build_bands_chart(sp500_series, thermo_series, "S&P 500 — Macro Risk Bands", show_event_markers=show_event_markers, log_scale=spx_log_scale)
        if fig_bands_spx is not None:
            sections.append({
                "type": "chart",
                "title": "Regimes — S&P 500 with risk bands",
                "caption": "Background color shows macro risk zone over time. Price (white line) on top.",
                "fig": fig_bands_spx,
            })
    if not btc_series.empty and not thermo_series.empty:
        fig_bands_btc = build_bands_chart(btc_series, thermo_series, "Bitcoin — Macro Risk Bands", show_event_markers=show_event_markers)
        if fig_bands_btc is not None:
            sections.append({
                "type": "chart",
                "title": "Regimes — Bitcoin with risk bands",
                "caption": "BTC price with same macro risk zone shading.",
                "fig": fig_bands_btc,
            })
    if not oil_price_series.empty and not thermo_series.empty:
        fig_bands_oil = build_bands_chart(oil_price_series, thermo_series, "WTI Oil — Macro Risk Bands", show_event_markers=show_event_markers)
        if fig_bands_oil is not None:
            sections.append({
                "type": "chart",
                "title": "Regimes — Oil (WTI) with risk bands",
                "caption": "Oil price with macro risk zone shading.",
                "fig": fig_bands_oil,
            })
    if fig4 is not None:
        sections.append({
            "type": "chart",
            "title": f"Regimes — {last_chart_header}",
            "caption": last_chart_desc,
            "fig": fig4,
        })

    return sections

# Initialize PNG bytes for PDF (set when each chart is built)
png_liq = png1 = png2 = png_yield = png_fci = png_credit = png3 = png4 = None

# ----- Tabs: Macro (Core) | Markets | Regimes & Bands | Fiscal -----
tab_macro, tab_markets, tab_regimes, tab_fiscal = st.tabs(["Macro (Core)", "Markets", "Regimes & Bands", "Fiscal"])

with tab_macro:
    st.markdown("#### Model Inputs")
    # Build macro model input variables: current value + 1Y ROC
    _fed = val_df["FEDFUNDS"].dropna() if not val_df.empty and "FEDFUNDS" in val_df.columns else pd.Series(dtype=float)
    _v = model_input_series.get("DGS2"); _dgs2 = _v if isinstance(_v, pd.Series) else pd.Series(dtype=float)
    _dgs10 = yield_df["DGS10"].dropna() if not yield_df.empty and "DGS10" in yield_df.columns else pd.Series(dtype=float)
    _cpi = risk_df["INFLATION"].dropna() if not risk_df.empty and "INFLATION" in risk_df.columns else pd.Series(dtype=float)
    _cpi_yoy = ((_cpi / _cpi.shift(12)) - 1) * 100 if len(_cpi) >= 13 else pd.Series(dtype=float)
    _v = model_input_series.get("CPILFESL"); _core_cpi = _v if isinstance(_v, pd.Series) else pd.Series(dtype=float)
    _core_cpi_yoy = ((_core_cpi / _core_cpi.shift(12)) - 1) * 100 if len(_core_cpi) >= 13 else pd.Series(dtype=float)
    _unemp = risk_df["UNEMPLOYMENT"].dropna() if not risk_df.empty and "UNEMPLOYMENT" in risk_df.columns else pd.Series(dtype=float)
    _v = model_input_series.get("ICSA"); _claims = _v if isinstance(_v, pd.Series) else pd.Series(dtype=float)
    _walcl = liquidity_df["WALCL"].dropna() if not liquidity_df.empty and "WALCL" in liquidity_df.columns else pd.Series(dtype=float)
    _hy = risk_df["CREDIT_STRESS"].dropna() if not risk_df.empty and "CREDIT_STRESS" in risk_df.columns else pd.Series(dtype=float)
    _nfci = risk_df["CREDIT_TIGHTENING"].dropna() if not risk_df.empty and "CREDIT_TIGHTENING" in risk_df.columns else pd.Series(dtype=float)
    _macro_inputs = []
    if not _fed.empty:
        _macro_inputs.append(("Fed Funds Rate", f"{_fed.iloc[-1]:.2f}%", _roc_1y(_fed, 12), True))
    if not _dgs2.empty:
        _macro_inputs.append(("2Y Treasury", f"{_dgs2.iloc[-1]:.2f}%", _roc_1y(_dgs2, 252), True))
    if not _dgs10.empty:
        _macro_inputs.append(("10Y Treasury", f"{_dgs10.iloc[-1]:.2f}%", _roc_1y(_dgs10, 252), True))
    if not _cpi_yoy.empty:
        _macro_inputs.append(("CPI YoY", f"{_cpi_yoy.iloc[-1]:.1f}%", _roc_1y(_cpi_yoy, 12), True))
    if not _core_cpi_yoy.empty:
        _macro_inputs.append(("Core CPI YoY", f"{_core_cpi_yoy.iloc[-1]:.1f}%", _roc_1y(_core_cpi_yoy, 12), True))
    if not _unemp.empty:
        _macro_inputs.append(("Unemployment", f"{_unemp.iloc[-1]:.1f}%", _roc_1y(_unemp, 12), True))
    if not _claims.empty:
        _macro_inputs.append(("Initial Claims", f"{_claims.iloc[-1]:,.0f}", _roc_1y(_claims, 52), True))
    if not _walcl.empty:
        _macro_inputs.append(("Fed Balance Sheet", f"{_walcl.iloc[-1]/1e9:.1f}B", _roc_1y(_walcl, 52), False))
    if liquidity_yoy_series is not None and not liquidity_yoy_series.empty:
        _macro_inputs.append(("Liquidity YoY", f"{liquidity_yoy_series.iloc[-1]:.1f}%", _roc_1y(liquidity_yoy_series, 52), False))
    if not _hy.empty:
        _macro_inputs.append(("HY OAS", f"{_hy.iloc[-1]:.2f}%", _roc_1y(_hy, 252), True))
    if not _nfci.empty:
        _macro_inputs.append(("NFCI", f"{_nfci.iloc[-1]:.3f}", _roc_1y(_nfci, 252), True))
    _model_input_cards(_macro_inputs)
    st.markdown("#### Today's Snapshot")
    with st.container():
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("Macro Risk", f"{macro_score}" if macro_score else "—", zone_label or "")
        with c2:
            st.metric("Liquidity", liquidity_status or "—", "WALCL YoY")
        with c3:
            spread_str = f"{last_spread_val:.2f}%" if last_spread_val is not None else "—"
            st.metric("Yield Curve (10Y–3M)", spread_str, yield_status or "")
        with c4:
            mom_str = f"{last_roc_90_val:.2f}" if last_roc_90_val is not None else "—"
            st.metric("YC Momentum (90d)", mom_str, yield_mom_status or "")
        with c5:
            st.metric("FCI", fci_status or "—", "NFCI")
        c6, c7, _ = st.columns([1, 1, 2])
        with c6:
            st.metric("Credit Spreads", credit_status or "—", "HY OAS")
    st.divider()

    # ----- Chart 1: Global Liquidity -----
    st.header("1. Global Liquidity")
    st.markdown(
        '<p class="section-desc">This chart tracks whether liquidity is expanding or contracting. '
        'Rising liquidity tends to support asset prices; falling liquidity can tighten financial conditions.</p>',
        unsafe_allow_html=True,
    )
    fig_liquidity = build_liquidity_chart(liquidity_df, show_event_markers=show_event_markers)
    if fig_liquidity is not None:
        st.plotly_chart(fig_liquidity, width="stretch", key="liquidity")
        png_liq, _ = _try_export_png(fig_liquidity)
        if png_liq is not None:
            st.download_button("Export PNG", data=png_liq, file_name="01_global_liquidity.png", mime="image/png", key="dl_liquidity")
    else:
        st.info("Not enough liquidity data. Check FRED series WALCL (need 53+ weekly points for YoY).")

    st.header("2. Stock Market Pressure")
    st.markdown(
        '<p class="section-desc">This chart measures how much pressure the overall economy is placing on stock prices. '
        'It combines major forces like interest rates, inflation, unemployment, and liquidity. '
        'Higher values mean more pressure on valuations, which can make it harder for the market to move higher. '
        'Lower values mean less pressure, which tends to support stocks.</p>',
        unsafe_allow_html=True,
    )
    fig1 = build_valuation_chart(val_df, overlay_series=overlay_val, show_event_markers=show_event_markers)
    if fig1 is not None:
        st.plotly_chart(fig1, width="stretch", key="vpi")
        png1, _ = _try_export_png(fig1)
        if png1 is not None:
            st.download_button("Export PNG", data=png1, file_name="02_stock_market_pressure.png", mime="image/png", key="dl_vpi")
    else:
        st.info("Not enough valuation data. Check FRED_API_KEY and series availability.")

    st.header("3. Economic Risk Index")
    st.markdown(
        '<p class="section-desc">This chart tracks the overall level of stress in the economy by combining multiple macro '
        'indicators into one score. The goal is to measure how stable or unstable the environment is for markets. '
        'The blue line shows current risk level, and the ROC line shows how quickly conditions are changing. '
        'Sharp increases often signal rising instability before markets fully react.</p>',
        unsafe_allow_html=True,
    )
    fig2 = build_macro_risk_chart(risk_df, overlay_series=overlay_risk, show_event_markers=show_event_markers)
    if fig2 is not None:
        st.plotly_chart(fig2, width="stretch", key="macro_risk")
        png2, _ = _try_export_png(fig2)
        if png2 is not None:
            st.download_button("Export PNG", data=png2, file_name="03_economic_risk_index.png", mime="image/png", key="dl_macro")
    else:
        st.info("Not enough macro risk data.")

    st.header("4. Yield Curve (10Y – 3M) + Momentum")
    st.markdown(
        '<p class="section-desc">This chart shows the difference between long-term and short-term U.S. Treasury interest rates. '
        'When short-term rates rise above long-term rates (an inverted yield curve), it has historically signaled increasing recession risk.</p>',
        unsafe_allow_html=True,
    )
    fig_yield = build_yield_curve_chart(yield_df, show_10y_3m_lines=show_10y_3m_lines, show_event_markers=show_event_markers)
    if fig_yield is not None:
        st.plotly_chart(fig_yield, width="stretch", key="yield_curve")
        png_yield, _ = _try_export_png(fig_yield)
        if png_yield is not None:
            st.download_button("Export PNG", data=png_yield, file_name="04_yield_curve_10y_3m.png", mime="image/png", key="dl_yield")
    else:
        st.info("Not enough yield curve data. Check FRED series DGS10 and DGS3MO.")

    st.header("5. Financial Conditions Index")
    st.markdown(
        '<p class="section-desc">Chicago Fed National Financial Conditions Index (NFCI). '
        'Higher values indicate tighter financial conditions (more stress); lower values indicate easier conditions (more support for risk assets). Zero is the baseline.</p>',
        unsafe_allow_html=True,
    )
    fig_fci = build_fci_chart(risk_df, show_ma=True, show_event_markers=show_event_markers)
    if fig_fci is not None:
        st.plotly_chart(fig_fci, width="stretch", key="fci")
        png_fci, _ = _try_export_png(fig_fci)
        if png_fci is not None:
            st.download_button("Export PNG", data=png_fci, file_name="05_financial_conditions_index.png", mime="image/png", key="dl_fci")
    else:
        st.info("Not enough data for Financial Conditions Index. NFCI (FRED) required.")

    st.header("6. Credit Spreads (High Yield OAS)")
    st.markdown(
        '<p class="section-desc">ICE BofA US High Yield Option-Adjusted Spread. '
        'Rising spreads mean credit is getting more expensive and stress is increasing. Reference lines: 3% (calm), 5% (stress rising), 7% (high stress).</p>',
        unsafe_allow_html=True,
    )
    fig_credit = build_credit_spreads_chart(risk_df, show_event_markers=show_event_markers)
    if fig_credit is not None:
        st.plotly_chart(fig_credit, width="stretch", key="credit")
        png_credit, _ = _try_export_png(fig_credit)
        if png_credit is not None:
            st.download_button("Export PNG", data=png_credit, file_name="06_credit_spreads.png", mime="image/png", key="dl_credit")
    else:
        st.info("Not enough data for Credit Spreads. BAMLH0A0HYM2 (FRED) required.")

    st.header("7. Market Risk Level (0–100)")
    st.markdown(
        '<p class="section-desc">This chart converts complex macro signals into a simple risk score from 0 to 100. '
        'Lower scores suggest a stable environment where markets typically perform better. '
        'Higher scores suggest growing stress in the financial system. '
        'The colored bands show whether conditions look very low risk through extreme risk.</p>',
        unsafe_allow_html=True,
    )
    fig3 = build_thermostat_chart(
        risk_df, overlay_series=overlay_risk, show_event_markers=show_event_markers
    )
    if fig3 is not None:
        latest = thermo_series.iloc[-1] if not thermo_series.empty else 0
        st.plotly_chart(fig3, width="stretch", key="thermo")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Current reading", f"{latest:.0f}", "0–100 scale")
        with col2:
            st.metric("Zone", _thermo_zone(latest), "")
        png3, _ = _try_export_png(fig3)
        if png3 is not None:
            st.download_button("Export PNG", data=png3, file_name="07_market_risk_level.png", mime="image/png", key="dl_thermo")
    else:
        st.info("Requires macro risk data.")

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
        _market_inputs.append(("S&P 500", f"{_sp500.iloc[-1]:,.0f}", _roc_1y(_sp500, 252), False))
    if not _wti.empty:
        _market_inputs.append(("WTI Oil", f"${_wti.iloc[-1]:.2f}", _roc_1y(_wti, 252), False))
    _model_input_cards(_market_inputs)
    st.markdown("#### Today's Snapshot")
    # BTC strip
    if btc_snapshot and btc_snapshot.get("price") is not None:
        st.caption("**BTC**")
        r1, r2, r3, r4, r5 = st.columns(5)
        with r1:
            st.metric("BTC Price", f"${btc_snapshot['price']:,.0f}" if btc_snapshot.get("price") else "—", "")
            for k in ["wma50", "wma100", "wma200", "wma300"]:
                v = btc_snapshot.get(k)
                st.caption(f"{k}: ${v:,.0f}" if v is not None else f"{k}: —")
        with r2:
            st.metric("Balanced (proxy)", f"${btc_snapshot['balanced_price']:,.0f}" if btc_snapshot.get("balanced_price") else "—", "")
            st.metric("Terminal (proxy)", f"${btc_snapshot['terminal_price']:,.0f}" if btc_snapshot.get("terminal_price") else "—", "")
        with r3:
            for label, key in [("1W", "roc1w"), ("4W", "roc4w"), ("12W", "roc12w"), ("52W", "roc52w")]:
                v = btc_snapshot.get(key)
                st.metric(f"ROC {label}", f"{v:.1f}%" if v is not None else "—", "")
        with r4:
            v200 = btc_snapshot.get("dist_200wma_pct")
            v300 = btc_snapshot.get("dist_300wma_pct")
            st.metric("Dist 200WMA", f"{v200:.1f}%" if v200 is not None else "—", "")
            st.metric("Dist 300WMA", f"{v300:.1f}%" if v300 is not None else "—", "")
        with r5:
            st.caption("WMAs = weighted moving avg (weekly)")
    # Oil snapshot
    if oil_snapshot:
        st.caption("**Oil (WTI)**")
        o1, o2, o3 = st.columns(3)
        with o1:
            st.metric("WTI Spot", f"${oil_snapshot.get('price', 0):.2f}" if oil_snapshot.get("price") is not None else "—", "")
        with o2:
            v = oil_snapshot.get("roc4w")
            st.metric("4W ROC", f"{v:.1f}%" if v is not None else "—", "")
        with o3:
            v = oil_snapshot.get("roc52w")
            st.metric("52W ROC", f"{v:.1f}%" if v is not None else "—", "")
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
        cpi_yoy_series=cpi_series,
        show_event_markers=show_event_markers,
    )
    if fig_oil is not None:
        st.plotly_chart(fig_oil, width="stretch", key="oil")
    else:
        st.info("Not enough oil data. Check FRED DCOILWTICO and API key.")

    st.header("Bitcoin (BTC/USD)")
    st.markdown(
        '<p class="section-desc">Bitcoin price from FRED (CBBTCUSD) or Yahoo Finance. Overlays: Liquidity YoY (WALCL), 10Y TIPS real yield.</p>',
        unsafe_allow_html=True,
    )
    fig_btc = build_bitcoin_chart(
        btc_series,
        log_scale=btc_log_scale,
        liquidity_yoy_series=liquidity_yoy_series if btc_show_liquidity else None,
        real_yield_series=real_yield_series if btc_show_real_yield else None,
        show_event_markers=show_event_markers,
    )
    if fig_btc is not None:
        st.plotly_chart(fig_btc, width="stretch", key="btc")
    else:
        st.info("Not enough Bitcoin data. Try FRED CBBTCUSD or Yahoo BTC-USD.")

    st.header("Bitcoin Rainbow (Log Regression Bands)")
    st.markdown(
        '<p class="section-desc">Log regression bands (full history); display follows lookback. Balanced = midline; Terminal = lower band (proxy).</p>',
        unsafe_allow_html=True,
    )
    obs_start = config.lookback_to_observation_start(lookback)
    fig_rainbow = build_btc_rainbow_chart(
        btc_series,
        display_start=obs_start,
        log_scale=btc_log_scale,
    )
    if fig_rainbow is not None:
        st.plotly_chart(fig_rainbow, width="stretch", key="btc_rainbow")
    else:
        st.info("Not enough BTC history for Rainbow (need 30+ points).")

with tab_regimes:
    st.markdown("#### Model Inputs")
    _spread_series = yield_df["DGS10"].sub(yield_df["DGS3MO"]).dropna() if not yield_df.empty and "DGS10" in yield_df.columns and "DGS3MO" in yield_df.columns else pd.Series(dtype=float)
    _regime_inputs = []
    if not thermo_series.empty:
        _regime_inputs.append(("Market Risk Score", f"{thermo_series.iloc[-1]:.0f}/100", _roc_1y(thermo_series, 252), True))
    if liquidity_yoy_series is not None and not liquidity_yoy_series.empty:
        _regime_inputs.append(("Liquidity YoY", f"{liquidity_yoy_series.iloc[-1]:.1f}%", _roc_1y(liquidity_yoy_series, 52), False))
    if not _spread_series.empty:
        _regime_inputs.append(("Yield Curve (10Y–3M)", f"{_spread_series.iloc[-1]:.2f}%", _roc_1y(_spread_series, 252), False))  # higher spread = steeper = better
    if not risk_df.empty and "CREDIT_STRESS" in risk_df.columns:
        _hy = risk_df["CREDIT_STRESS"].dropna()
        if not _hy.empty:
            _regime_inputs.append(("Credit Spread", f"{_hy.iloc[-1]:.2f}%", _roc_1y(_hy, 252), True))
    if not risk_df.empty and "CREDIT_TIGHTENING" in risk_df.columns:
        _n = risk_df["CREDIT_TIGHTENING"].dropna()
        if not _n.empty:
            _regime_inputs.append(("NFCI", f"{_n.iloc[-1]:.3f}", _roc_1y(_n, 252), True))
    _model_input_cards(_regime_inputs)
    st.markdown("#### Today's Snapshot")
    r1, r2, r3, r4, r5 = st.columns(5)
    with r1:
        risk_val = thermo_series.iloc[-1] if not thermo_series.empty else None
        zone = _regime_zone_label_6(risk_val) if risk_val is not None else "—"
        st.metric("Risk score", f"{risk_val:.0f}/100" if risk_val is not None else "—", zone)
    with r2:
        liq_yoy = None
        if liquidity_yoy_series is not None and not liquidity_yoy_series.empty:
            liq_yoy = float(liquidity_yoy_series.iloc[-1])
        st.metric("Liquidity YoY", f"{liq_yoy:.1f}%" if liq_yoy is not None else "—", "WALCL")
    with r3:
        spread_str = f"{last_spread_val:.2f}%" if last_spread_val is not None else "—"
        mom_str = f"{last_roc_90_val:.2f}" if last_roc_90_val is not None else "—"
        st.metric("Yield curve (10Y–3M)", spread_str, yield_status or "")
        st.caption(f"Momentum (90d): {mom_str}")
    with r4:
        hy = None
        if not risk_df.empty and "CREDIT_STRESS" in risk_df.columns:
            s = risk_df["CREDIT_STRESS"].dropna()
            hy = float(s.iloc[-1]) if len(s) else None
        st.metric("HY OAS", f"{hy:.2f}%" if hy is not None else "—", "")
    with r5:
        nfci = None
        if not risk_df.empty and "CREDIT_TIGHTENING" in risk_df.columns:
            s = risk_df["CREDIT_TIGHTENING"].dropna()
            nfci = float(s.iloc[-1]) if len(s) else None
        st.metric("NFCI", f"{nfci:.3f}" if nfci is not None else "—", "FCI")
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
            st.plotly_chart(fig_bands_spx, width="stretch", key="bands_spx")
    else:
        st.info("Need valuation and risk data for S&P 500 bands.")

    if not btc_series.empty and not thermo_series.empty:
        st.subheader("Bitcoin with risk bands")
        st.caption("BTC price with same macro risk zone shading.")
        fig_bands_btc = build_bands_chart(btc_series, thermo_series, "Bitcoin — Macro Risk Bands", show_event_markers=show_event_markers)
        if fig_bands_btc is not None:
            st.plotly_chart(fig_bands_btc, width="stretch", key="bands_btc")
    else:
        st.info("Need Bitcoin and risk data for bands.")

    oil_price_series = oil_df["DCOILWTICO"].dropna() if not oil_df.empty and "DCOILWTICO" in oil_df.columns else pd.Series(dtype=float)
    if not oil_price_series.empty and not thermo_series.empty:
        st.subheader("Oil (WTI) with risk bands")
        st.caption("Oil price with macro risk zone shading.")
        fig_bands_oil = build_bands_chart(oil_price_series, thermo_series, "WTI Oil — Macro Risk Bands", show_event_markers=show_event_markers)
        if fig_bands_oil is not None:
            st.plotly_chart(fig_bands_oil, width="stretch", key="bands_oil")
    else:
        st.info("Need oil and risk data for bands.")

    st.subheader(last_chart_header)
    st.markdown(f'<p class="section-desc">{last_chart_desc}</p>', unsafe_allow_html=True)
    if fig4 is not None:
        st.plotly_chart(fig4, width="stretch", key="rotation")
        png4, _ = _try_export_png(fig4)
        if png4 is not None:
            st.download_button("Export PNG", data=png4, file_name="08_rotation_ladder.png", mime="image/png", key="dl_rot")
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
        _fiscal_inputs.append(("Annual Deficit % GDP", f"{_def_pct.iloc[-1]:.2f}%", _roc_1y(_def_pct, 1), True))  # annual
    if not _debt_pct.empty:
        _fiscal_inputs.append(("Debt-to-GDP", f"{_debt_pct.iloc[-1]:.1f}%", _roc_1y(_debt_pct, 1), True))  # annual
    if not _net_int.empty:
        _fiscal_inputs.append(("Net Interest ($B)", f"{_net_int.iloc[-1]:.1f}", _roc_1y(_net_int, 4), True))  # quarterly
    if not _int_pct.empty:
        _fiscal_inputs.append(("Interest % GDP", f"{_int_pct.iloc[-1]:.2f}%", _roc_1y(_int_pct, 4), True))  # quarterly
    _model_input_cards(_fiscal_inputs)
    st.markdown("#### Fiscal Snapshot")
    f1, f2, f3 = st.columns(3)
    with f1:
        st.metric("Deficit % GDP", f"{_def_pct.iloc[-1]:.2f}%" if not _def_pct.empty else "—", "")
    with f2:
        st.metric("Debt-to-GDP", f"{_debt_pct.iloc[-1]:.1f}%" if not _debt_pct.empty else "—", "")
    with f3:
        st.metric("Interest Burden", f"{_int_pct.iloc[-1]:.2f}%" if not _int_pct.empty else "—", "% of GDP")
    st.divider()

    st.header("1. Annual Deficit (% of GDP)")
    st.markdown(
        '<p class="section-desc">This chart shows how much the federal government is spending beyond its income relative to the size of the economy. Higher values mean fiscal imbalances are becoming larger.</p>',
        unsafe_allow_html=True,
    )
    fig_deficit = build_deficit_pct_gdp_chart(fiscal_df, show_event_markers=show_event_markers)
    if fig_deficit is not None:
        st.plotly_chart(fig_deficit, width="stretch", key="fiscal_deficit")
    else:
        st.info("Not enough fiscal data. Check FRED series FYFSGDA188S (Surplus/Deficit as % GDP).")

    st.header("2. Federal Debt-to-GDP")
    st.markdown(
        '<p class="section-desc">This chart shows the size of the national debt relative to the economy. Rising levels suggest the debt burden is becoming harder to manage over time.</p>',
        unsafe_allow_html=True,
    )
    fig_debt = build_debt_to_gdp_chart(fiscal_df, show_event_markers=show_event_markers)
    if fig_debt is not None:
        st.plotly_chart(fig_debt, width="stretch", key="fiscal_debt")
    else:
        st.info("Not enough fiscal data. Check FRED series FYGFDPUN (Debt % GDP).")

    st.header("3. Net Interest Expense Burden")
    st.markdown(
        '<p class="section-desc">This chart shows how much of the government\'s financial capacity is being consumed by interest payments on the debt. Rising values can reduce flexibility and increase long-term fiscal risk. Shown as percent of GDP.</p>',
        unsafe_allow_html=True,
    )
    fig_interest = build_interest_burden_chart(fiscal_df, show_event_markers=show_event_markers)
    if fig_interest is not None:
        st.plotly_chart(fig_interest, width="stretch", key="fiscal_interest")
    else:
        st.info("Not enough fiscal data. Check FRED series B091RC1Q027SBEA (Net interest) and GDP.")

# ----- Generate PDF (all 3 tabs + Executive Summary + Macro Radar) -----
if pdf_available() and build_dashboard_pdf:
    def _pdf_export_fn(fig):
        if fig is None:
            return None
        png, _ = _try_export_png(_fig_for_pdf(fig))
        return png

    _pdf_export_error = None
    for _fig in (fig_liquidity, fig1, fig2, fig_yield, fig_fci, fig_credit, fig3, fig4):
        if _fig is not None:
            _, _err = _try_export_png(_fig)
            if _err is not None:
                _pdf_export_error = _err
            break

    try:
        _pdf_sections = _build_pdf_sections(
            lookback=lookback,
            show_event_markers=show_event_markers,
            show_10y_3m_lines=show_10y_3m_lines,
            show_market_overlay=show_market_overlay,
            oil_log_scale=oil_log_scale,
            oil_show_yoy=oil_show_yoy,
            oil_show_cpi=oil_show_cpi,
            btc_log_scale=btc_log_scale,
            btc_show_liquidity=btc_show_liquidity,
            btc_show_real_yield=btc_show_real_yield,
            btc_rainbow_k=btc_rainbow_k,
            spx_log_scale=spx_log_scale,
            use_fred_only_last_chart=use_fred_only_last_chart,
            val_df=val_df,
            risk_df=risk_df,
            yield_df=yield_df,
            liquidity_df=liquidity_df,
            rot_df=rot_df,
            oil_df=oil_df,
            btc_series=btc_series,
            real_yield_series=real_yield_series,
            ladder_df=ladder_df,
            overlay_val=overlay_val,
            overlay_risk=overlay_risk,
            thermo_series=thermo_series,
            liquidity_yoy_series=liquidity_yoy_series,
            cpi_series=cpi_series,
            ai_summary=(ai_result if (enable_ai and ai_result and not ai_result.get("_error")) else None),
            macro_drivers=macro_drivers_list if include_macro_drivers else [],
        )
        # Pre-export chart figures to PNG so the PDF can embed them (avoids repeated export in builder)
        for sec in _pdf_sections:
            if sec.get("type") == "chart" and sec.get("fig") is not None:
                png = _pdf_export_fn(sec["fig"])
                if png is not None:
                    sec["fig"] = png
        pdf_bytes = build_dashboard_pdf(
            _pdf_sections,
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
        if _pdf_export_error is not None:
            with st.expander("Why are charts missing from the PDF?"):
                st.code(_pdf_export_error, language="text")
                st.markdown(
                    "Charts are exported with **Playwright** (headless Chromium). Install once:\n\n"
                    "```bash\npip install playwright\npython -m playwright install chromium\n```\n\n"
                    "Then restart the app. On Streamlit Cloud, Chromium may not be available; the PDF will still include the summary and AI text."
                )
    except Exception as e:
        st.caption(f"PDF could not be generated: {e}")

st.markdown("""
<div class="footer">
    Private Macro Dashboard · <a href="https://github.com" target="_blank" rel="noopener">GitHub</a> · 
    FRED + Yahoo Finance · Export PNG for newsletter
</div>
""", unsafe_allow_html=True)
