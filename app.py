"""
Macro Dashboard — Private, local-first. Run: streamlit run app.py
"""
from __future__ import annotations

import io
import os

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
    build_thermostat_chart,
    build_rotation_chart,
)
from data import fetch_valuation_data, fetch_macro_risk_data, fetch_yield_curve_data, fetch_rotation_data
from models import compute_macro_risk_composite, compute_risk_thermostat


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
</style>
""", unsafe_allow_html=True)

st.markdown("# Macro Dashboard")
st.markdown('<p class="subtitle">Valuation pressure · Macro risk · Yield curve · Risk thermostat · Rotation</p>', unsafe_allow_html=True)

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

# Sidebar: refresh, lookback, market overlay
with st.sidebar:
    st.subheader("Data")
    lookback = st.selectbox("Macro lookback", config.LOOKBACK_OPTIONS, index=2)  # 5y default
    show_market_overlay = st.checkbox("Show Market Overlay (S&P 500)", value=False)
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
    try:
        rot_df = fetch_rotation_data(period=rot_period)
    except Exception:
        rot_df = pd.DataFrame()
    return val_df, risk_df, yield_df, rot_df

try:
    val_df, risk_df, yield_df, rot_df = load_all(lookback)
except Exception as e:
    st.error(f"Data load failed: {e}")
    val_df, risk_df, yield_df, rot_df = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

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


# ----- Chart 1: Stock Market Pressure -----
st.header("1. Stock Market Pressure")
st.markdown(
    '<p class="section-desc">This chart measures how much pressure the overall economy is placing on stock prices. '
    'It combines major forces like interest rates, inflation, unemployment, and liquidity. '
    'Higher values mean more pressure on valuations, which can make it harder for the market to move higher. '
    'Lower values mean less pressure, which tends to support stocks.</p>',
    unsafe_allow_html=True,
)
fig1 = build_valuation_chart(val_df, overlay_series=overlay_val)
if fig1 is not None:
    st.plotly_chart(fig1, width="stretch", key="vpi")
    png1, _ = _try_export_png(fig1)
    if png1 is not None:
        st.download_button("Export PNG", data=png1, file_name="01_valuation_pressure_index.png", mime="image/png", key="dl_vpi")
else:
    st.info("Not enough valuation data. Check FRED_API_KEY and series availability.")

# ----- Chart 2: Economic Risk Index -----
st.header("2. Economic Risk Index")
st.markdown(
    '<p class="section-desc">This chart tracks the overall level of stress in the economy by combining multiple macro '
    'indicators into one score. The goal is to measure how stable or unstable the environment is for markets. '
    'The blue line shows current risk level, and the ROC line shows how quickly conditions are changing. '
    'Sharp increases often signal rising instability before markets fully react.</p>',
    unsafe_allow_html=True,
)
fig2 = build_macro_risk_chart(risk_df, overlay_series=overlay_risk)
if fig2 is not None:
    st.plotly_chart(fig2, width="stretch", key="macro_risk")
    png2, _ = _try_export_png(fig2)
    if png2 is not None:
        st.download_button("Export PNG", data=png2, file_name="02_macro_risk_raw_roc.png", mime="image/png", key="dl_macro")
else:
    st.info("Not enough macro risk data.")

# ----- Chart 3: Yield Curve (10Y – 3M) -----
st.header("3. Yield Curve (10Y – 3M)")
st.markdown(
    '<p class="section-desc">This chart shows the difference between long-term and short-term U.S. Treasury interest rates. '
    'When short-term rates rise above long-term rates (an inverted yield curve), it has historically signaled increasing recession risk.</p>',
    unsafe_allow_html=True,
)
fig_yield = build_yield_curve_chart(yield_df)
if fig_yield is not None:
    st.plotly_chart(fig_yield, width="stretch", key="yield_curve")
    png_yield, _ = _try_export_png(fig_yield)
    if png_yield is not None:
        st.download_button("Export PNG", data=png_yield, file_name="03_yield_curve_10y_3m.png", mime="image/png", key="dl_yield")
else:
    st.info("Not enough yield curve data. Check FRED series DGS10 and DGS3MO.")

# ----- Chart 4: Market Risk Level 0–100 -----
st.header("4. Market Risk Level (0–100)")
st.markdown(
    '<p class="section-desc">This chart converts complex macro signals into a simple risk score from 0 to 100. '
    'Lower scores suggest a stable environment where markets typically perform better. '
    'Higher scores suggest growing stress in the financial system. '
    'The colored bands show whether conditions look very low risk through extreme risk.</p>',
    unsafe_allow_html=True,
)
fig3 = build_thermostat_chart(risk_df, overlay_series=overlay_risk)
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
        st.download_button("Export PNG", data=png3, file_name="04_market_risk_level.png", mime="image/png", key="dl_thermo")
else:
    st.info("Requires macro risk data.")

# ----- Chart 5: Risk Cascade (Rotation) -----
st.header("5. Risk Cascade Curves (Rotation)")
st.markdown(
    '<p class="section-desc">This chart shows how different parts of the market are performing relative to each other over time. '
    'Each line is rebased to 100 at the start so you can see which segments are strengthening or weakening. '
    'It helps spot when investors are moving into safer assets (defensives) or taking more risk (small caps, crypto).</p>',
    unsafe_allow_html=True,
)
fig4 = build_rotation_chart(rot_df)
if fig4 is not None:
    st.plotly_chart(fig4, width="stretch", key="rotation")
    png4, _ = _try_export_png(fig4)
    if png4 is not None:
        st.download_button("Export PNG", data=png4, file_name="05_risk_cascade_rotation.png", mime="image/png", key="dl_rot")
else:
    st.info("Rotation data (Yahoo Finance) could not be loaded.")

st.markdown("""
<div class="footer">
    Private Macro Dashboard · <a href="https://github.com" target="_blank" rel="noopener">GitHub</a> · 
    FRED + Yahoo Finance · Export PNG for newsletter
</div>
""", unsafe_allow_html=True)
