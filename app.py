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

# Streamlit Cloud: secrets in st.secrets; put FRED_API_KEY into env so config/data layers see it
try:
    if hasattr(st, "secrets"):
        val = getattr(st.secrets, "get", lambda k: None)("FRED_API_KEY") or getattr(st.secrets, "FRED_API_KEY", None)
        if not val and "FRED_API_KEY" in st.secrets:
            val = st.secrets["FRED_API_KEY"]
        if val:
            os.environ.setdefault("FRED_API_KEY", str(val))
except Exception:
    pass

import config

# Server-side log: appears in Streamlit Cloud "Manage app" → Logs (not in browser console)
print(f"[Macro Dashboard] FRED_API_KEY set: {bool(config.FRED_API_KEY)}")

from charts.build import (
    build_valuation_chart,
    build_macro_risk_chart,
    build_yield_curve_chart,
    build_liquidity_chart,
    build_fci_chart,
    build_credit_spreads_chart,
    build_thermostat_chart,
    build_rotation_chart,
    build_curves_chart,
    build_oil_chart,
    build_bitcoin_chart,
    build_bands_chart,
    build_rotation_ladder_chart,
    build_btc_rainbow_chart,
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
)
from data.market_data import fetch_rotation_ladder_data
from models import compute_macro_risk_composite, compute_risk_thermostat, prepare_regime_curves
from models.btc_metrics import compute_btc_snapshot

try:
    from pdf_report import build_dashboard_pdf, pdf_available
except ImportError:
    build_dashboard_pdf = None
    pdf_available = lambda: False


def _try_export_png(fig):
    """Export Plotly figure to PNG bytes. Returns (bytes, None) or (None, error_msg).
    On Streamlit Cloud, Kaleido requires Chrome which is not installed, so we skip export gracefully.
    """
    try:
        buf = io.BytesIO()
        fig.write_image(buf, format="png", scale=2)
        buf.seek(0)
        return buf.getvalue(), None
    except Exception as e:
        return None, str(e)


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
st.markdown('<p class="subtitle">Macro (Core) · Markets (Oil, BTC) · Regimes & Bands</p>', unsafe_allow_html=True)

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
    return val_df, risk_df, yield_df, liquidity_df, rot_df, oil_df, btc_series, real_yield_series, ladder_df

try:
    val_df, risk_df, yield_df, liquidity_df, rot_df, oil_df, btc_series, real_yield_series, ladder_df = load_all(lookback)
except Exception as e:
    st.error(f"Data load failed: {e}")
    val_df = risk_df = yield_df = liquidity_df = rot_df = oil_df = pd.DataFrame()
    btc_series = real_yield_series = pd.Series(dtype=float)
    ladder_df = pd.DataFrame()

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

# Build Tab 3 "last" chart once for PDF (rotation ladder or FRED regime)
fig4 = None
last_chart_header = "8. Rotation Ladder"
last_chart_desc = "Z-score normalized relative strength ratios (risk-on → defensive). Higher line = that ratio outperforming."
if use_fred_only_last_chart or ladder_df.empty:
    regime_curves = prepare_regime_curves(val_df, risk_df)
    fig4 = build_curves_chart(regime_curves, title="Macro Regime (FRED) — 100 = start")
    last_chart_header = "8. Macro Regime (FRED)"
    last_chart_desc = "FRED-only: S&P 500, Liquidity (WALCL), NFCI, HY spread — rebased to 100 at start."
else:
    fig4 = build_rotation_ladder_chart(ladder_df)

# Initialize PNG bytes for PDF (set when each chart is built)
png_liq = png1 = png2 = png_yield = png_fci = png_credit = png3 = png4 = None

# ----- Tabs: Macro (Core) | Markets | Regimes & Bands -----
tab_macro, tab_markets, tab_regimes = st.tabs(["Macro (Core)", "Markets", "Regimes & Bands"])

with tab_macro:
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

# ----- Generate PDF -----
if pdf_available() and build_dashboard_pdf:
    _section_descs = [
        "This chart tracks whether liquidity is expanding or contracting. Rising liquidity tends to support asset prices; falling liquidity can tighten financial conditions.",
        "This chart measures how much pressure the overall economy is placing on stock prices. It combines major forces like interest rates, inflation, unemployment, and liquidity. Higher values mean more pressure on valuations; lower values tend to support stocks.",
        "This chart tracks the overall level of stress in the economy by combining multiple macro indicators into one score. The blue line shows current risk level; the ROC line shows how quickly conditions are changing.",
        "This chart shows the difference between long-term and short-term U.S. Treasury interest rates. An inverted yield curve has historically signaled increasing recession risk.",
        "Chicago Fed National Financial Conditions Index (NFCI). Higher values indicate tighter conditions; lower values indicate easier conditions. Zero is the baseline.",
        "ICE BofA US High Yield Option-Adjusted Spread. Rising spreads mean credit is getting more expensive and stress is increasing. Reference lines: 3%% (calm), 5%% (stress rising), 7%% (high stress).",
        "This chart converts complex macro signals into a simple risk score from 0 to 100. Lower scores suggest a stable environment; higher scores suggest growing stress. Bands indicate very low through extreme risk.",
        last_chart_desc,
    ]
    # Pass figures so PDF can export at build time (embeds charts when Kaleido works)
    _pdf_sections = [
        ("1. Global Liquidity", _section_descs[0], fig_liquidity),
        ("2. Stock Market Pressure", _section_descs[1], fig1),
        ("3. Economic Risk Index", _section_descs[2], fig2),
        ("4. Yield Curve (10Y – 3M) + Momentum", _section_descs[3], fig_yield),
        ("5. Financial Conditions Index", _section_descs[4], fig_fci),
        ("6. Credit Spreads (High Yield OAS)", _section_descs[5], fig_credit),
        ("7. Market Risk Level (0–100)", _section_descs[6], fig3),
        (last_chart_header, _section_descs[7], fig4),
    ]
    _readout = ""
    if macro_score and zone_label:
        _readout += f"Macro Risk: {macro_score} ({zone_label}). "
    if liquidity_status:
        _readout += f"Liquidity: {liquidity_status}. "
    if yield_status:
        _readout += f"Yield curve: {yield_status}. "
    if fci_status:
        _readout += f"Financial conditions: {fci_status}. "
    if credit_status:
        _readout += f"Credit stress: {credit_status}."
    # Diagnose why chart export might fail (so user sees the real error)
    _pdf_export_error = None
    for _fig in (fig_liquidity, fig1, fig2, fig_yield, fig_fci, fig_credit, fig3, fig4):
        if _fig is not None:
            _, _err = _try_export_png(_fig)
            if _err is not None:
                _pdf_export_error = _err
            break
    try:
        pdf_bytes = build_dashboard_pdf(
            _pdf_sections,
            report_date=date.today().isoformat(),
            readout_text=_readout.strip() or None,
            export_fn=lambda fig: (_try_export_png(_fig_for_pdf(fig))[0] if fig is not None else None),
        )
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="macro_dashboard.pdf",
            mime="application/pdf",
            key="dl_pdf",
        )
        if _pdf_export_error is not None:
            with st.expander("Why are charts missing from the PDF?"):
                st.code(_pdf_export_error, language="text")
                st.markdown(
                    "Charts need **Kaleido** to export Plotly figures to PNG. "
                    "Install: `pip install kaleido --upgrade`. "
                    "If Kaleido 1.x complains about Chrome, run in a terminal: "
                    "`python -c \"import kaleido; kaleido.get_chrome_sync()\"`"
                )
    except Exception as e:
        st.caption(f"PDF could not be generated: {e}")

st.markdown("""
<div class="footer">
    Private Macro Dashboard · <a href="https://github.com" target="_blank" rel="noopener">GitHub</a> · 
    FRED + Yahoo Finance · Export PNG for newsletter
</div>
""", unsafe_allow_html=True)
