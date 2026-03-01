"""
Macro Dashboard — Private, local-first. Run: streamlit run app.py
"""
from __future__ import annotations

import io

import pandas as pd
from dotenv import load_dotenv

load_dotenv()
import streamlit as st

import config
from charts.build import (
    build_valuation_chart,
    build_macro_risk_chart,
    build_thermostat_chart,
    build_rotation_chart,
)
from data import fetch_valuation_data, fetch_macro_risk_data, fetch_rotation_data
from models import compute_macro_risk_composite, compute_risk_thermostat

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
st.markdown('<p class="subtitle">Valuation pressure · Macro risk · Risk thermostat · Rotation</p>', unsafe_allow_html=True)

if not config.FRED_API_KEY:
    st.warning(
        "Set **FRED_API_KEY** in your environment (or `.env`) to load macro data. "
        "[Get a free key](https://fred.stlouisfed.org/docs/api/api_key.html)."
    )

# Sidebar: refresh and lookback
with st.sidebar:
    st.subheader("Data")
    lookback = st.selectbox("Macro lookback", config.LOOKBACK_OPTIONS, index=2)  # 5y default
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

@st.cache_data(ttl=3600)
def load_all(lookback: str):
    obs_start = config.lookback_to_observation_start(lookback)
    rot_period = config.lookback_to_rotation_period(lookback)
    val_df = fetch_valuation_data(observation_start=obs_start)
    risk_df = fetch_macro_risk_data(observation_start=obs_start)
    rot_df = fetch_rotation_data(period=rot_period)
    return val_df, risk_df, rot_df

try:
    val_df, risk_df, rot_df = load_all(lookback)
except Exception as e:
    st.error(f"Data load failed: {e}")
    val_df, risk_df, rot_df = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# ----- Chart 1: Valuation Pressure Index -----
st.header("1. Valuation Pressure Index")
st.markdown(
    '<p class="section-desc">Macro-driven valuation compression pressure on equities. Rising = tightening; falling = easing.</p>',
    unsafe_allow_html=True,
)
fig1 = build_valuation_chart(val_df)
if fig1 is not None:
    st.plotly_chart(fig1, use_container_width=True, key="vpi")
    buf1 = io.BytesIO()
    fig1.write_image(buf1, format="png", scale=2)
    st.download_button("Export PNG", data=buf1.getvalue(), file_name="01_valuation_pressure_index.png", mime="image/png", key="dl_vpi")
else:
    st.info("Not enough valuation data. Check FRED_API_KEY and series availability.")

# ----- Chart 2: Macro Risk (Raw + ROC) -----
st.header("2. Macro Risk Dashboard")
st.markdown(
    '<p class="section-desc">Raw standardized composite + ROC (acceleration). Rising = deterioration; falling = stabilization.</p>',
    unsafe_allow_html=True,
)
fig2 = build_macro_risk_chart(risk_df)
if fig2 is not None:
    st.plotly_chart(fig2, use_container_width=True, key="macro_risk")
    buf2 = io.BytesIO()
    fig2.write_image(buf2, format="png", scale=2)
    st.download_button("Export PNG", data=buf2.getvalue(), file_name="02_macro_risk_raw_roc.png", mime="image/png", key="dl_macro")
else:
    st.info("Not enough macro risk data.")

# ----- Chart 3: Risk Thermostat 0–100 -----
st.header("3. Risk Thermostat (0–100)")
st.markdown(
    '<p class="section-desc">Allocation guide: 0–25 Risk-on · 25–50 Neutral · 50–70 De-risk · 70–85 Defensive · 85–100 Capital preservation</p>',
    unsafe_allow_html=True,
)
fig3 = build_thermostat_chart(risk_df)
if fig3 is not None:
    raw = compute_macro_risk_composite(risk_df)
    thermo = compute_risk_thermostat(raw)
    latest = thermo.iloc[-1] if not thermo.empty else 0
    st.plotly_chart(fig3, use_container_width=True, key="thermo")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Current reading", f"{latest:.0f}", "0–100 scale")
    with col2:
        zone = "Risk-on" if latest < 25 else "Neutral" if latest < 50 else "De-risk high beta" if latest < 70 else "Defensive rotation" if latest < 85 else "Capital preservation"
        st.metric("Zone", zone, "")
    buf3 = io.BytesIO()
    fig3.write_image(buf3, format="png", scale=2)
    st.download_button("Export PNG", data=buf3.getvalue(), file_name="03_risk_thermostat.png", mime="image/png", key="dl_thermo")
else:
    st.info("Requires macro risk data.")

# ----- Chart 4: Risk Cascade (Rotation) -----
st.header("4. Risk Cascade Curves (Rotation)")
st.markdown(
    '<p class="section-desc">Relative strength ratios (rebased 100). Risk escalates: alts → BTC → small cap → credit → defensives.</p>',
    unsafe_allow_html=True,
)
fig4 = build_rotation_chart(rot_df)
if fig4 is not None:
    st.plotly_chart(fig4, use_container_width=True, key="rotation")
    buf4 = io.BytesIO()
    fig4.write_image(buf4, format="png", scale=2)
    st.download_button("Export PNG", data=buf4.getvalue(), file_name="04_risk_cascade_rotation.png", mime="image/png", key="dl_rot")
else:
    st.info("Rotation data (Yahoo Finance) could not be loaded.")

st.markdown("""
<div class="footer">
    Private Macro Dashboard · <a href="https://github.com" target="_blank" rel="noopener">GitHub</a> · 
    FRED + Yahoo Finance · Export PNG for newsletter
</div>
""", unsafe_allow_html=True)
