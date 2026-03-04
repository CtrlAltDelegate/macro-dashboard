"""
Macro Dashboard — Private, local-first. Run: streamlit run app.py
"""
from __future__ import annotations

import io
import os
from datetime import date

import pandas as pd
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
)
from data import fetch_valuation_data, fetch_macro_risk_data, fetch_yield_curve_data, fetch_liquidity_data, fetch_rotation_data
from models import compute_macro_risk_composite, compute_risk_thermostat, prepare_rotation_curves, prepare_regime_curves

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
</style>
""", unsafe_allow_html=True)

st.markdown("# Macro Dashboard")
st.markdown('<p class="subtitle">Global Liquidity · Stock Market Pressure · Economic Risk · Yield Curve · Financial Conditions · Credit Spreads · Market Risk Level · Rotation</p>', unsafe_allow_html=True)

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
    use_fred_only_last_chart = st.checkbox(
        "Use FRED only for last chart (no Yahoo)",
        value=False,
        help="Use macro series from FRED only for chart 8. No API key; works when Yahoo is blocked or rate-limited.",
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
    return val_df, risk_df, yield_df, liquidity_df, rot_df

try:
    val_df, risk_df, yield_df, liquidity_df, rot_df = load_all(lookback)
except Exception as e:
    st.error(f"Data load failed: {e}")
    val_df, risk_df, yield_df, liquidity_df, rot_df = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

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

# Initialize PNG bytes for PDF (set when each chart is built)
png_liq = png1 = png2 = png_yield = png_fci = png_credit = png3 = png4 = None

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

# ----- Chart 2: Stock Market Pressure -----
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

# ----- Chart 3: Economic Risk Index -----
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

# ----- Chart 4: Yield Curve (10Y – 3M) + Momentum -----
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

# ----- Chart 5: Financial Conditions Index -----
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

# ----- Chart 6: Credit Spreads -----
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

# ----- Chart 7: Market Risk Level 0–100 -----
st.header("7. Market Risk Level (0–100)")
st.markdown(
    '<p class="section-desc">This chart converts complex macro signals into a simple risk score from 0 to 100. '
    'Lower scores suggest a stable environment where markets typically perform better. '
    'Higher scores suggest growing stress in the financial system. '
    'The colored bands show whether conditions look very low risk through extreme risk.</p>',
    unsafe_allow_html=True,
)
fig3 = build_thermostat_chart(risk_df, overlay_series=overlay_risk, show_event_markers=show_event_markers)
if fig3 is not None:
    raw = compute_macro_risk_composite(risk_df)
    thermo = compute_risk_thermostat(raw)
    latest = thermo.iloc[-1] if not thermo.empty else 0
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

# ----- Chart 8: Risk Cascade (Rotation) or Macro Regime (FRED) -----
use_fred_for_last = use_fred_only_last_chart or rot_df.empty
if use_fred_for_last:
    regime_curves = prepare_regime_curves(val_df, risk_df)
    fig4 = build_curves_chart(regime_curves, title="Macro Regime (FRED) — 100 = start")
    last_chart_header = "8. Macro Regime (FRED)"
    last_chart_desc = (
        "This chart uses only FRED data (no Yahoo): S&P 500, Fed liquidity (WALCL), "
        "Financial Conditions (NFCI), and High Yield spread — each rebased to 100 at the start. "
        "Use it when Yahoo Finance is unavailable or you prefer FRED-only sources."
    )
    last_chart_filename = "08_macro_regime_fred.png"
else:
    fig4 = build_rotation_chart(rot_df)
    last_chart_header = "8. Risk Cascade Curves (Rotation)"
    last_chart_desc = (
        "This chart shows how different parts of the market are performing relative to each other over time. "
        "Each line is rebased to 100 at the start so you can see which segments are strengthening or weakening. "
        "It helps spot when investors are moving into safer assets (defensives) or taking more risk (small caps, crypto)."
    )
    last_chart_filename = "08_risk_cascade_rotation.png"

st.header(last_chart_header)
st.markdown(f'<p class="section-desc">{last_chart_desc}</p>', unsafe_allow_html=True)
if fig4 is not None:
    st.plotly_chart(fig4, width="stretch", key="rotation")
    png4, _ = _try_export_png(fig4)
    if png4 is not None:
        st.download_button("Export PNG", data=png4, file_name=last_chart_filename, mime="image/png", key="dl_rot")
else:
    st.info("Chart data could not be loaded. Try \"Use FRED only for last chart\" if Yahoo fails.")

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
    try:
        pdf_bytes = build_dashboard_pdf(
            _pdf_sections,
            report_date=date.today().isoformat(),
            readout_text=_readout.strip() or None,
            export_fn=lambda fig: (_try_export_png(fig)[0] if fig is not None else None),
        )
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="macro_dashboard.pdf",
            mime="application/pdf",
            key="dl_pdf",
        )
    except Exception as e:
        st.caption(f"PDF could not be generated: {e}")

st.markdown("""
<div class="footer">
    Private Macro Dashboard · <a href="https://github.com" target="_blank" rel="noopener">GitHub</a> · 
    FRED + Yahoo Finance · Export PNG for newsletter
</div>
""", unsafe_allow_html=True)
