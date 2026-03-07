"""
Build Plotly figures for all four dashboard charts. Shared by app.py and refresh.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .theme import apply_theme, AXIS_LIGHT
from models import (
    compute_valuation_pressure_index,
    compute_macro_risk_composite,
    compute_macro_risk_roc,
    compute_risk_thermostat,
    prepare_rotation_curves,
    prepare_rotation_zscore,
    prepare_regime_curves,
)
from models.btc_metrics import btc_rainbow_regression

# Risk band thresholds and labels (0–100 scale)
THERMO_BANDS = [(0, 20, "Very Low Risk"), (20, 40, "Low Risk"), (40, 60, "Moderate Risk"), (60, 80, "High Risk"), (80, 100, "Extreme Risk")]
THERMO_HLINES = [20, 40, 60, 80]

# Regimes & Bands tab: 6 zones (user-specified)
REGIME_BANDS_6 = [
    (0, 20, "Very Low Risk", "rgba(63, 185, 80, 0.22)"),
    (20, 40, "Low Risk", "rgba(88, 166, 255, 0.2)"),
    (40, 60, "Moderate Risk", "rgba(210, 153, 34, 0.25)"),
    (60, 75, "High Risk", "rgba(248, 140, 60, 0.28)"),
    (75, 90, "Very High Risk", "rgba(248, 81, 73, 0.3)"),
    (90, 100, "Extreme Risk", "rgba(139, 50, 50, 0.35)"),
]

OVERLAY_COLOR = "rgba(140, 140, 140, 0.65)"
OVERLAY_LINE = dict(color=OVERLAY_COLOR, width=1.2, dash="dash")

# Macro Radar: pillar names and scoring (0–100, higher = worse risk)
RADAR_PILLARS = [
    "Liquidity",
    "Yield Curve",
    "Credit",
    "Financial Conditions",
    "Inflation",
    "Labor",
    "Market Risk",
]


def _score_liquidity_yoy(yoy: float | None) -> float:
    """Map WALCL YoY % to risk 0–100. Positive YoY = low risk, negative = high."""
    if yoy is None:
        return 50.0
    if yoy >= 10:
        return 10.0
    if yoy >= 0:
        return 15.0 + (10 - yoy) * 2.0  # 0->35, 10->15
    if yoy >= -5:
        return 35.0 + (-yoy) * 6.0  # 0->35, -5->65
    return min(95.0, 65.0 + (-5 - yoy) * 4.0)


def _score_yield_curve(spread: float | None) -> float:
    """Map 10Y–3M spread to risk 0–100. Inverted = high risk."""
    if spread is None:
        return 50.0
    if spread >= 1.5:
        return 20.0
    if spread >= 0:
        return 20.0 + (1.5 - spread) * 20.0  # 1.5->20, 0->50
    return min(100.0, 50.0 + (-spread) * 25.0)


def _score_credit_hy(oas: float | None) -> float:
    """Map HY OAS % to risk 0–100."""
    if oas is None:
        return 50.0
    if oas <= 3:
        return 15.0 + oas * 3.33
    if oas <= 7:
        return 25.0 + (oas - 3) * 13.75  # 3->25, 7->80
    return min(100.0, 80.0 + (oas - 7) * 7.5)


def _score_nfci(nfci: float | None) -> float:
    """Map NFCI to risk 0–100. Tighter (positive) = higher risk."""
    if nfci is None:
        return 50.0
    # NFCI typically -1 to +1; 0 = neutral
    return float(np.clip(50.0 + nfci * 50.0, 0, 100))


def _score_inflation_yoy(cpi_yoy: float | None) -> float:
    """Map CPI YoY % to risk 0–100."""
    if cpi_yoy is None:
        return 50.0
    if cpi_yoy <= 2:
        return 20.0 + cpi_yoy * 5.0
    if cpi_yoy <= 6:
        return 30.0 + (cpi_yoy - 2) * 10.0  # 2->30, 6->70
    return min(100.0, 70.0 + (cpi_yoy - 6) * 7.5)


def _score_labor(unemployment: float | None) -> float:
    """Map unemployment rate to risk 0–100."""
    if unemployment is None:
        return 50.0
    if unemployment <= 4:
        return 20.0 + unemployment * 5.0
    if unemployment <= 7:
        return 40.0 + (unemployment - 4) * 15.0
    return min(100.0, 85.0 + (unemployment - 7) * 5.0)


def compute_radar_pillar_scores(
    risk_df: pd.DataFrame,
    liquidity_df: pd.DataFrame,
    yield_df: pd.DataFrame,
    thermo_series: pd.Series,
) -> dict[str, float]:
    """Compute 0–100 risk score per pillar (higher = worse). Returns dict of pillar name -> score."""
    scores: dict[str, float] = {p: 50.0 for p in RADAR_PILLARS}

    # Liquidity: WALCL YoY
    if not liquidity_df.empty and "WALCL" in liquidity_df.columns:
        walcl = liquidity_df["WALCL"].dropna()
        if len(walcl) >= 53:
            yoy = ((walcl / walcl.shift(52)) - 1) * 100
            yoy = yoy.dropna()
            if not yoy.empty:
                scores["Liquidity"] = _score_liquidity_yoy(float(yoy.iloc[-1]))

    # Yield curve: 10Y – 3M
    if not yield_df.empty and "DGS10" in yield_df.columns and "DGS3MO" in yield_df.columns:
        spread = yield_df["DGS10"].sub(yield_df["DGS3MO"]).dropna()
        if not spread.empty:
            scores["Yield Curve"] = _score_yield_curve(float(spread.iloc[-1]))

    # Credit: HY OAS
    if not risk_df.empty and "CREDIT_STRESS" in risk_df.columns:
        hy = risk_df["CREDIT_STRESS"].dropna()
        if not hy.empty:
            scores["Credit"] = _score_credit_hy(float(hy.iloc[-1]))

    # Financial Conditions: NFCI
    if not risk_df.empty and "CREDIT_TIGHTENING" in risk_df.columns:
        nfci = risk_df["CREDIT_TIGHTENING"].dropna()
        if not nfci.empty:
            scores["Financial Conditions"] = _score_nfci(float(nfci.iloc[-1]))

    # Inflation: CPI YoY
    if not risk_df.empty and "INFLATION" in risk_df.columns:
        cpi = risk_df["INFLATION"].dropna()
        if len(cpi) >= 13:
            cpi_yoy = ((cpi / cpi.shift(12)) - 1) * 100
            cpi_yoy = cpi_yoy.dropna()
            if not cpi_yoy.empty:
                scores["Inflation"] = _score_inflation_yoy(float(cpi_yoy.iloc[-1]))

    # Labor: Unemployment
    if not risk_df.empty and "UNEMPLOYMENT" in risk_df.columns:
        u = risk_df["UNEMPLOYMENT"].dropna()
        if not u.empty:
            scores["Labor"] = _score_labor(float(u.iloc[-1]))

    # Market Risk: thermostat (already 0–100)
    if not thermo_series.empty:
        scores["Market Risk"] = float(thermo_series.iloc[-1])

    return scores


def build_macro_radar_chart(
    risk_df: pd.DataFrame,
    liquidity_df: pd.DataFrame,
    yield_df: pd.DataFrame,
    thermo_series: pd.Series,
) -> go.Figure | None:
    """
    Macro Radar (spider chart): 7 pillars, 0–100 risk per axis (higher = worse).
    Dark theme, fill='toself', hover shows current value.
    """
    scores_dict = compute_radar_pillar_scores(risk_df, liquidity_df, yield_df, thermo_series)
    values = [scores_dict[p] for p in RADAR_PILLARS]
    categories = RADAR_PILLARS

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=values + [values[0]],
            theta=categories + [categories[0]],
            fill="toself",
            fillcolor="rgba(88, 166, 255, 0.35)",
            line=dict(color="#58a6ff", width=2),
            name="Risk score",
            hovertemplate="%{theta}: %{r:.0f}/100<extra></extra>",
        )
    )
    fig.update_layout(
        polar=dict(
            bgcolor="#0d1117",
            radialaxis=dict(
                range=[0, 100],
                tickvals=[20, 40, 60, 80],
                gridcolor="#30363d",
                linecolor="#8b949e",
                tickfont=dict(color="#8b949e", size=10),
            ),
            angularaxis=dict(
                gridcolor="#30363d",
                linecolor="#8b949e",
                tickfont=dict(color="#8b949e", size=11),
            ),
        ),
        title=dict(
            text="Macro Radar — Risk by pillar (0–100, higher = worse)",
            font=dict(size=14, color="#e6edf3"),
            x=0.5,
            xanchor="center",
        ),
        paper_bgcolor="#0d1117",
        showlegend=False,
        margin=dict(l=80, r=80, t=48, b=48),
        height=380,
    )
    return fig


# Optional event markers (vertical lines)
EVENT_MARKERS = [
    ("2020-03-16", "COVID crash"),
    ("2022-03-16", "2022 tightening"),
    ("2023-03-10", "2023 banking stress"),
]


def _add_event_markers(fig: go.Figure, enabled: bool) -> None:
    """Add vertical reference lines for key macro events when enabled."""
    if not enabled:
        return
    for date_str, label in EVENT_MARKERS:
        fig.add_vline(
            x=date_str,
            line_dash="dot",
            line_color="rgba(139, 148, 158, 0.6)",
            line_width=1,
            annotation_text=label,
            annotation_position="top",
            annotation_font_size=10,
            annotation_font_color="rgba(139, 148, 158, 0.9)",
        )


def _add_market_overlay(fig: go.Figure, overlay_series: pd.Series, use_secondary_y: bool = False) -> None:
    """Add optional S&P 500 overlay (normalized to 100 at start). Light gray, dashed, thin.
    If use_secondary_y, add overlay on y2 and configure layout.yaxis2."""
    if overlay_series is None or overlay_series.empty:
        return
    s = overlay_series.dropna()
    if s.empty or len(s) < 2:
        return
    trace_kw = dict(
        x=s.index,
        y=s.values,
        mode="lines",
        name="S&P 500 (rebased)",
        line=OVERLAY_LINE,
    )
    if use_secondary_y:
        trace_kw["yaxis"] = "y2"
    fig.add_trace(go.Scatter(**trace_kw))
    if use_secondary_y:
        fig.update_layout(
            yaxis2=dict(
                overlaying="y",
                side="right",
                showgrid=False,
                zeroline=False,
                linecolor="rgba(140,140,140,0.5)",
                tickfont=dict(color="rgba(140,140,140,0.9)", size=11),
                title=None,
            ),
        )


def build_valuation_chart(
    val_df: pd.DataFrame,
    overlay_series: pd.Series | None = None,
    show_event_markers: bool = False,
) -> go.Figure | None:
    if val_df.empty or len(val_df) < 10:
        return None
    vpi = compute_valuation_pressure_index(val_df)
    if vpi.empty:
        return None
    base = vpi.iloc[0]
    vpi_rebase = (vpi / base) * 100 if base != 0 else vpi
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=vpi_rebase.index, y=vpi_rebase.values, mode="lines",
        name="Stock Market Pressure (rebased)", line=dict(color="#58a6ff", width=2)
    ))
    _add_market_overlay(fig, overlay_series, use_secondary_y=False)
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "Stock Market Pressure (rebased to 100)", height=380)
    return fig


def build_macro_risk_chart(
    risk_df: pd.DataFrame,
    overlay_series: pd.Series | None = None,
    show_event_markers: bool = False,
) -> go.Figure | None:
    if risk_df.empty or len(risk_df) < 60:
        return None
    raw = compute_macro_risk_composite(risk_df)
    roc = compute_macro_risk_roc(raw, period=21)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=raw.index, y=raw.values, mode="lines", name="Raw composite", line=dict(color="#58a6ff", width=2)))
    fig.add_trace(go.Scatter(x=roc.index, y=roc.values, mode="lines", name="ROC (21-period)", line=dict(color="#d29922", width=1.5)))
    _add_market_overlay(fig, overlay_series, use_secondary_y=True)
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "Economic Risk Index — Raw & ROC", height=380)
    return fig


def build_yield_curve_chart(
    yield_df: pd.DataFrame,
    show_10y_3m_lines: bool = False,
    show_event_markers: bool = False,
) -> go.Figure | None:
    """Build yield curve spread chart (10Y – 3M), 20-period MA, ROC, inversion shading."""
    if yield_df.empty or len(yield_df) < 20:
        return None
    if "DGS10" not in yield_df.columns or "DGS3MO" not in yield_df.columns:
        return None
    spread = yield_df["DGS10"].sub(yield_df["DGS3MO"]).dropna()
    if spread.empty or len(spread) < 20:
        return None
    smoothed = spread.rolling(window=20, min_periods=1).mean()
    # 90-day momentum (ROC): spread - spread.shift(90)
    roc_90d = spread - spread.shift(90)
    roc_90d = roc_90d.dropna()
    # Raw 10Y and 3M aligned to smoothed index (for hover tooltip)
    d10 = yield_df["DGS10"].reindex(smoothed.index).ffill().bfill()
    d3 = yield_df["DGS3MO"].reindex(smoothed.index).ffill().bfill()
    customdata = list(zip(d10.values, d3.values))
    # Inversion fill: only where smoothed < 0 (clip to zero so fill is from line to 0)
    y_fill = smoothed.clip(upper=0)
    fig = go.Figure()
    # Light red shading for inversion periods (below 0) — no hover to avoid clutter
    fig.add_trace(go.Scatter(
        x=y_fill.index,
        y=y_fill.values,
        mode="lines",
        fill="tozeroy",
        line=dict(width=0),
        fillcolor="rgba(248, 81, 73, 0.18)",
        name="Inversion (spread < 0)",
        showlegend=True,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=smoothed.index,
        y=smoothed.values,
        mode="lines",
        name="10Y – 3M (20-period MA)",
        line=dict(color="#d4a017", width=2.5),
        customdata=customdata,
        hovertemplate=(
            "Date: %{x|%Y-%m-%d}<br>"
            "10Y Yield: %{customdata[0]:.2f}%<br>"
            "3M Yield: %{customdata[1]:.2f}%<br>"
            "Spread: %{y:.2f}%<extra></extra>"
        ),
    ))
    if not roc_90d.empty:
        fig.add_trace(go.Scatter(
            x=roc_90d.index,
            y=roc_90d.values,
            mode="lines",
            name="Spread ROC (90d)",
            line=dict(color="#a371f7", width=1.5, dash="dash"),
            hovertemplate="Date: %{x|%Y-%m-%d}<br>ROC (90d): %{y:.2f}%<extra></extra>",
        ))
    # Optional overlay: 10Y and 3M on secondary y-axis (faint)
    if show_10y_3m_lines:
        d10_ = yield_df["DGS10"].reindex(smoothed.index).ffill().bfill()
        d3_ = yield_df["DGS3MO"].reindex(smoothed.index).ffill().bfill()
        fig.add_trace(go.Scatter(
            x=d10_.index, y=d10_.values, mode="lines",
            name="10Y yield", line=dict(color="rgba(210, 153, 23, 0.4)", width=1),
            yaxis="y2",
        ))
        fig.add_trace(go.Scatter(
            x=d3_.index, y=d3_.values, mode="lines",
            name="3M yield", line=dict(color="rgba(139, 148, 158, 0.5)", width=1),
            yaxis="y2",
        ))
        fig.update_layout(
            yaxis2=dict(
                overlaying="y", side="right", showgrid=False, zeroline=False,
                linecolor="rgba(139,148,158,0.4)", tickfont=dict(color="rgba(139,148,158,0.8)", size=10), title=None,
            ),
        )
    # 0% = inversion threshold (red); 1.5% = healthy curve (green)
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(248, 81, 73, 0.9)", line_width=1.2)
    fig.add_hline(y=1.5, line_dash="dash", line_color="rgba(63, 185, 80, 0.8)", line_width=1)
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "Yield Curve (10Y – 3M) + Momentum", height=380)
    return fig


def build_liquidity_chart(
    liquidity_df: pd.DataFrame,
    show_event_markers: bool = False,
) -> go.Figure | None:
    """Build Global Liquidity chart: Fed balance sheet (WALCL) year-over-year % change."""
    if liquidity_df.empty or "WALCL" not in liquidity_df.columns:
        return None
    walcl = liquidity_df["WALCL"].dropna()
    if len(walcl) < 53:  # need 52+ points for YoY
        return None
    # LiquidityYoY = ((WALCL / WALCL.shift(52)) - 1) * 100 (weekly → 52 weeks = 1 year)
    yoy = ((walcl / walcl.shift(52)) - 1) * 100
    yoy = yoy.dropna()
    if yoy.empty:
        return None
    walcl_aligned = walcl.reindex(yoy.index).ffill().bfill()
    customdata = list(zip(walcl_aligned.values / 1e9, yoy.values))  # WALCL in billions for readability
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=yoy.index,
        y=yoy.values,
        mode="lines",
        name="Liquidity YoY %",
        line=dict(color="#3fb950", width=2.5),
        customdata=customdata,
        hovertemplate=(
            "Date: %{x|%Y-%m-%d}<br>"
            "WALCL: %{customdata[0]:,.1f}B<br>"
            "YoY: %{y:.2f}%<extra></extra>"
        ),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(139, 148, 158, 0.9)", line_width=1.2)
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "Global Liquidity (YoY %)", height=380)
    return fig


def build_fci_chart(
    risk_df: pd.DataFrame,
    show_ma: bool = True,
    show_event_markers: bool = False,
) -> go.Figure | None:
    """Financial Conditions Index — Chicago Fed NFCI. Higher = tighter conditions."""
    if risk_df.empty or "CREDIT_TIGHTENING" not in risk_df.columns:
        return None
    nfci = risk_df["CREDIT_TIGHTENING"].dropna()
    if nfci.empty or len(nfci) < 20:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=nfci.index, y=nfci.values, mode="lines",
        name="NFCI", line=dict(color="#58a6ff", width=2),
        hovertemplate="Date: %{x|%Y-%m-%d}<br>NFCI: %{y:.3f}<extra></extra>",
    ))
    if show_ma and len(nfci) >= 20:
        ma = nfci.rolling(20, min_periods=1).mean()
        fig.add_trace(go.Scatter(
            x=ma.index, y=ma.values, mode="lines",
            name="NFCI (20-period MA)", line=dict(color="#d29922", width=1.5, dash="dash"),
            hovertemplate="Date: %{x|%Y-%m-%d}<br>NFCI MA: %{y:.3f}<extra></extra>",
        ))
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(139, 148, 158, 0.9)", line_width=1.2)
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "Financial Conditions Index (NFCI)", height=380)
    return fig


def build_credit_spreads_chart(
    risk_df: pd.DataFrame,
    show_event_markers: bool = False,
) -> go.Figure | None:
    """Credit Spreads — ICE BofA US High Yield OAS. Rising = stress increasing."""
    if risk_df.empty or "CREDIT_STRESS" not in risk_df.columns:
        return None
    hy = risk_df["CREDIT_STRESS"].dropna()
    if hy.empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hy.index, y=hy.values, mode="lines",
        name="HY OAS %", line=dict(color="#f85149", width=2),
        hovertemplate="Date: %{x|%Y-%m-%d}<br>Spread: %{y:.2f}%<extra></extra>",
    ))
    for y, label in [(3, "Calm"), (5, "Stress rising"), (7, "High stress")]:
        fig.add_hline(y=y, line_dash="dash", line_color="rgba(139, 148, 158, 0.7)", line_width=1)
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "Credit Spreads (High Yield OAS)", height=380)
    return fig


def build_deficit_pct_gdp_chart(
    fiscal_df: pd.DataFrame,
    show_event_markers: bool = False,
) -> go.Figure | None:
    """Annual Deficit (% of GDP). Higher = larger fiscal imbalance."""
    if fiscal_df.empty or "DEFICIT_PCT_GDP" not in fiscal_df.columns:
        return None
    s = fiscal_df["DEFICIT_PCT_GDP"].dropna()
    if s.empty or len(s) < 2:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines",
        name="Deficit % GDP", line=dict(color="#f85149", width=2),
        hovertemplate="Date: %{x|%Y-%m-%d}<br>Deficit: %{y:.2f}% of GDP<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(139, 148, 158, 0.9)", line_width=1.2)
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "1. Annual Deficit (% of GDP)", height=380)
    return fig


def build_debt_to_gdp_chart(
    fiscal_df: pd.DataFrame,
    show_event_markers: bool = False,
) -> go.Figure | None:
    """Federal Debt as % of GDP. Rising = higher debt burden."""
    if fiscal_df.empty or "DEBT_PCT_GDP" not in fiscal_df.columns:
        return None
    s = fiscal_df["DEBT_PCT_GDP"].dropna()
    if s.empty or len(s) < 2:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines",
        name="Debt % GDP", line=dict(color="#58a6ff", width=2),
        hovertemplate="Date: %{x|%Y-%m-%d}<br>Debt-to-GDP: %{y:.1f}%<extra></extra>",
    ))
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "2. Federal Debt-to-GDP", height=380)
    return fig


def build_interest_burden_chart(
    fiscal_df: pd.DataFrame,
    show_event_markers: bool = False,
) -> go.Figure | None:
    """Net Interest as % of GDP (debt service burden). Rising = less fiscal flexibility."""
    if fiscal_df.empty or "INTEREST_PCT_GDP" not in fiscal_df.columns:
        return None
    s = fiscal_df["INTEREST_PCT_GDP"].dropna()
    if s.empty or len(s) < 2:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines",
        name="Net interest % GDP", line=dict(color="#d29922", width=2),
        hovertemplate="Date: %{x|%Y-%m-%d}<br>Interest burden: %{y:.2f}% of GDP<extra></extra>",
    ))
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "3. Net Interest Expense Burden", height=380)
    return fig


def build_thermostat_chart(
    risk_df: pd.DataFrame,
    overlay_series: pd.Series | None = None,
    show_event_markers: bool = False,
) -> go.Figure | None:
    if risk_df.empty or len(risk_df) < 60:
        return None
    raw = compute_macro_risk_composite(risk_df)
    thermo = compute_risk_thermostat(raw)
    if thermo.empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=thermo.index, y=thermo.values, mode="lines", name="Market Risk Level", line=dict(color="#58a6ff", width=2)))
    for y in THERMO_HLINES:
        fig.add_hline(y=y, line_dash="dash", line_color="rgba(139, 148, 158, 0.8)")
    _add_market_overlay(fig, overlay_series, use_secondary_y=True)
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "Market Risk Level (0–100)", height=380)
    fig.update_yaxes(range=[0, 100])
    return fig


def build_curves_chart(
    curves_df: pd.DataFrame,
    title: str = "Relative strength (100 = start)",
) -> go.Figure | None:
    """Build a multi-series chart from a DataFrame of rebased curves (e.g. rotation or FRED regime)."""
    if curves_df.empty or len(curves_df.columns) == 0:
        return None
    fig = go.Figure()
    colors_list = ["#f85149", "#d29922", "#58a6ff", "#a371f7", "#3fb950"]
    for i, col in enumerate(curves_df.columns):
        fig.add_trace(go.Scatter(
            x=curves_df.index,
            y=curves_df[col].values,
            mode="lines",
            name=col,
            line=dict(color=colors_list[i % len(colors_list)], width=1.5),
        ))
    apply_theme(fig, title, height=400)
    return fig


def build_oil_chart(
    oil_df: pd.DataFrame,
    log_scale: bool = False,
    show_yoy: bool = False,
    cpi_yoy_series: pd.Series | None = None,
    show_event_markers: bool = False,
) -> go.Figure | None:
    """WTI spot oil (DCOILWTICO). Optional: log scale, YoY % line, CPI YoY overlay."""
    if oil_df.empty or "DCOILWTICO" not in oil_df.columns:
        return None
    price = oil_df["DCOILWTICO"].dropna()
    if price.empty or len(price) < 2:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=price.index, y=price.values, mode="lines", name="WTI spot ($)",
        line=dict(color="#d4a017", width=2),
        hovertemplate="Date: %{x|%Y-%m-%d}<br>WTI: $%{y:,.2f}<extra></extra>",
    ))
    if show_yoy and len(price) >= 253:
        yoy = ((price / price.shift(252)) - 1) * 100
        yoy = yoy.dropna()
        if not yoy.empty:
            fig.add_trace(go.Scatter(
                x=yoy.index, y=yoy.values, mode="lines", name="Oil YoY %",
                line=dict(color="#a371f7", width=1.5, dash="dash"),
                yaxis="y2",
                hovertemplate="Date: %{x|%Y-%m-%d}<br>YoY: %{y:.1f}%<extra></extra>",
            ))
            fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, zeroline=True, zerolinecolor="rgba(139,148,158,0.5)", tickfont=dict(color=AXIS_LIGHT, size=11), title=None))
    if cpi_yoy_series is not None and not cpi_yoy_series.empty and len(cpi_yoy_series) >= 13:
        cpi_yoy = ((cpi_yoy_series / cpi_yoy_series.shift(12)) - 1) * 100
        cpi_yoy = cpi_yoy.dropna()
        common = cpi_yoy.index.intersection(price.index)
        if len(common) >= 10:
            cpi_aligned = cpi_yoy.reindex(price.index).ffill().bfill()
            fig.add_trace(go.Scatter(
                x=cpi_aligned.index, y=cpi_aligned.values, mode="lines", name="CPI YoY %",
                line=dict(color="rgba(248, 81, 73, 0.8)", width=1.5, dash="dot"),
                yaxis="y2",
                hovertemplate="Date: %{x|%Y-%m-%d}<br>CPI YoY: %{y:.1f}%<extra></extra>",
            ))
            if "yaxis2" not in fig.layout or fig.layout.yaxis2 is None:
                fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, zeroline=True, zerolinecolor="rgba(139,148,158,0.5)", tickfont=dict(color=AXIS_LIGHT, size=11), title=None))
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "WTI Crude Oil (DCOILWTICO)", height=380)
    if log_scale:
        fig.update_yaxes(type="log")
    return fig


def build_bitcoin_chart(
    btc_series: pd.Series,
    log_scale: bool = True,
    liquidity_yoy_series: pd.Series | None = None,
    real_yield_series: pd.Series | None = None,
    show_event_markers: bool = False,
) -> go.Figure | None:
    """Bitcoin price (FRED CBBTCUSD or yfinance BTC-USD). Optional: Liquidity YoY, Real yields (DFII10) overlays."""
    if btc_series is None or btc_series.empty or len(btc_series) < 2:
        return None
    price = btc_series.ffill().dropna()
    if price.empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=price.index, y=price.values, mode="lines", name="BTC/USD",
        line=dict(color="#f0c14b", width=2),
        hovertemplate="Date: %{x|%Y-%m-%d}<br>BTC: $%{y:,.0f}<extra></extra>",
    ))
    secondary_added = False
    # liquidity_yoy_series: pre-computed WALCL YoY % (or raw WALCL; we compute YoY if len >= 53)
    if liquidity_yoy_series is not None and not liquidity_yoy_series.empty:
        ly = liquidity_yoy_series
        if len(ly) >= 53 and hasattr(ly, "shift"):
            yoy = ((ly / ly.shift(52)) - 1) * 100
            yoy = yoy.dropna()
        else:
            yoy = ly.dropna()
        if len(yoy) >= 5:
            yoy_aligned = yoy.reindex(price.index).ffill().bfill()
            if yoy_aligned.notna().sum() >= 5:
                fig.add_trace(go.Scatter(
                    x=yoy_aligned.index, y=yoy_aligned.values, mode="lines", name="Liquidity YoY %",
                    line=dict(color="#3fb950", width=1.5, dash="dash"), yaxis="y2",
                    hovertemplate="Date: %{x|%Y-%m-%d}<br>Liquidity YoY: %{y:.1f}%<extra></extra>",
                ))
                secondary_added = True
    if real_yield_series is not None and not real_yield_series.empty:
        ry = real_yield_series.reindex(price.index).ffill().bfill().dropna()
        if len(ry) >= 5:
            fig.add_trace(go.Scatter(
                x=ry.index, y=ry.values, mode="lines", name="10Y TIPS yield %",
                line=dict(color="#58a6ff", width=1.5, dash="dot"), yaxis="y2",
                hovertemplate="Date: %{x|%Y-%m-%d}<br>Real yield: %{y:.2f}%<extra></extra>",
            ))
            secondary_added = True
    if secondary_added:
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, zeroline=True, zerolinecolor="rgba(139,148,158,0.5)", tickfont=dict(color=AXIS_LIGHT, size=11), title=None))
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, "Bitcoin (BTC/USD)", height=380)
    if log_scale:
        fig.update_yaxes(type="log")
    return fig


def _zone_index(risk_val: float) -> int:
    """Return 0..5 for REGIME_BANDS_6."""
    for i, (lo, hi, _label, _color) in enumerate(REGIME_BANDS_6):
        if lo <= risk_val < hi:
            return i
    if risk_val >= 100:
        return 5
    return 0


def _zone_label(risk_val: float) -> str:
    """Return zone label (e.g. 'Low Risk') for risk score 0–100."""
    idx = _zone_index(risk_val)
    return REGIME_BANDS_6[idx][2]


def build_bands_chart(
    price_series: pd.Series,
    risk_score_series: pd.Series,
    title: str,
    show_event_markers: bool = False,
    log_scale: bool = False,
) -> go.Figure | None:
    """Asset price with background shading by macro risk zone (0–100). Hover: date, price, risk, zone."""
    if price_series is None or price_series.empty or risk_score_series is None or risk_score_series.empty:
        return None
    price = price_series.ffill().dropna()
    if len(price) < 2:
        return None
    risk_aligned = risk_score_series.reindex(price.index).ffill().bfill().dropna()
    if risk_aligned.empty:
        return None
    zones = risk_aligned.apply(_zone_index)
    shapes = []
    i = 0
    while i < len(zones):
        z = zones.iloc[i]
        j = i
        while j < len(zones) and zones.iloc[j] == z:
            j += 1
        _, _, _label, color = REGIME_BANDS_6[z]
        x0 = zones.index[i]
        x1 = zones.index[j - 1] if j > i else zones.index[i]
        shapes.append(dict(
            type="rect",
            xref="x", yref="paper",
            x0=x0, x1=x1, y0=0, y1=1,
            fillcolor=color,
            line=dict(width=0),
            layer="below",
        ))
        i = j
    risk_vals = risk_aligned.reindex(price.index).ffill().bfill()
    zone_labels = risk_vals.apply(_zone_label)
    customdata = np.column_stack([risk_vals.values, np.asarray(zone_labels)])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=price.index, y=price.values, mode="lines", name="Price",
        line=dict(color="#e6edf3", width=2),
        customdata=customdata,
        hovertemplate="Date: %{x|%Y-%m-%d}<br>Price: %{y:,.2f}<br>Risk: %{customdata[0]:.0f}<br>Zone: %{customdata[1]}<extra></extra>",
    ))
    fig.update_layout(shapes=shapes)
    _add_event_markers(fig, show_event_markers)
    apply_theme(fig, title, height=380)
    if log_scale:
        fig.update_yaxes(type="log")
    return fig


def build_rotation_chart(rot_df: pd.DataFrame) -> go.Figure | None:
    """Build rotation chart from Yahoo ratio data. Returns None if empty."""
    if rot_df.empty:
        return None
    curves = prepare_rotation_curves(rot_df)
    return build_curves_chart(curves, title="Rotation — Relative strength (100 = start)")


# Rainbow: fill between adjacent k-bands; gradient blue (low k) → red (high k)
RAINBOW_GRADIENT = [
    "rgba(88, 166, 255, 0.4)",   # -2 to -1.5
    "rgba(88, 166, 255, 0.35)",
    "rgba(63, 185, 80, 0.35)",
    "rgba(63, 185, 80, 0.3)",
    "rgba(210, 153, 34, 0.3)",   # -0.5 to 0
    "rgba(210, 153, 34, 0.35)",
    "rgba(248, 140, 60, 0.35)",
    "rgba(248, 81, 73, 0.4)",    # 1.5 to 2
]


def build_btc_rainbow_chart(
    btc_series: pd.Series,
    display_start: str | None = None,
    k_bands: list[float] | None = None,
    log_scale: bool = True,
) -> go.Figure | None:
    """
    Bitcoin Rainbow (log regression bands). ln(price)=a+b*ln(t); band_k = exp(ln_hat + k*sigma).
    Full history for regression; display by lookback. Fill between adjacent bands (blue→red).
    Hover: Date, price, band zone, midline, lower (k=-2), upper (k=+2).
    """
    from models.btc_metrics import RAINBOW_K_LIST

    if btc_series is None or btc_series.empty or len(btc_series) < 30:
        return None
    if k_bands is None:
        k_bands = RAINBOW_K_LIST
    result = btc_rainbow_regression(btc_series, t0_date="2010-07-17", k_bands=k_bands)
    if result is None:
        return None
    price_full, midline_full, bands, _a, _b, _stdev = result
    if display_start:
        try:
            cut = pd.Timestamp(display_start)
            price = price_full.loc[price_full.index >= cut]
            midline = midline_full.loc[midline_full.index >= cut]
            if price.empty or midline.empty:
                price, midline = price_full, midline_full
                bands_slice = bands
            else:
                bands_slice = {k: v.loc[v.index >= cut] for k, v in bands.items()}
        except Exception:
            price, midline = price_full, midline_full
            bands_slice = bands
    else:
        price, midline = price_full, midline_full
        bands_slice = bands
    if price.empty or midline.empty:
        return None
    sorted_k = sorted(bands_slice.keys())
    band_curves = {k: bands_slice[k].reindex(price.index).ffill().bfill() for k in sorted_k}
    lower_band = band_curves.get(-2.0)
    upper_band = band_curves.get(2.0)
    mid_aligned = midline.reindex(price.index).ffill().bfill()

    fig = go.Figure()
    # Fills between adjacent bands (8 regions)
    for i in range(len(sorted_k) - 1):
        k_lo, k_hi = sorted_k[i], sorted_k[i + 1]
        y_lo = band_curves[k_lo].values
        y_hi = band_curves[k_hi].values
        color = RAINBOW_GRADIENT[i % len(RAINBOW_GRADIENT)]
        fig.add_trace(go.Scatter(x=price.index, y=y_lo, mode="lines", line=dict(width=0), fill="tonexty", fillcolor=color, hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=price.index, y=y_hi, mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
    # Midline (k=0)
    fig.add_trace(go.Scatter(
        x=midline.index, y=midline.values, mode="lines", name="Balanced (midline)",
        line=dict(color="#8b949e", width=1.5, dash="dash"),
        hovertemplate="Date: %{x|%Y-%m-%d}<br>Midline: $%{y:,.0f}<extra></extra>",
    ))
    # Zone label per point: which [k_lo, k_hi] does price fall in?
    zone_labels = []
    for j in range(len(price)):
        p = price.iloc[j]
        z = "—"
        for i in range(len(sorted_k) - 1):
            k_lo, k_hi = sorted_k[i], sorted_k[i + 1]
            b_lo = band_curves[k_lo].iloc[j] if j < len(band_curves[k_lo]) else np.nan
            b_hi = band_curves[k_hi].iloc[j] if j < len(band_curves[k_hi]) else np.nan
            if pd.notna(b_lo) and pd.notna(b_hi) and min(b_lo, b_hi) <= p <= max(b_lo, b_hi):
                z = f"k={k_lo} to {k_hi}"
                break
        zone_labels.append(z)
    customdata = np.column_stack([
        np.asarray(zone_labels),
        mid_aligned.values,
        lower_band.values if lower_band is not None else np.full(len(price), np.nan),
        upper_band.values if upper_band is not None else np.full(len(price), np.nan),
    ])
    fig.add_trace(go.Scatter(
        x=price.index, y=price.values, mode="lines", name="BTC price",
        line=dict(color="#f0c14b", width=2),
        customdata=customdata,
        hovertemplate=(
            "Date: %{x|%Y-%m-%d}<br>BTC: $%{y:,.0f}<br>Zone: %{customdata[0]}<br>"
            "Midline: $%{customdata[1]:,.0f}<br>Lower (k=-2): $%{customdata[2]:,.0f}<br>Upper (k=+2): $%{customdata[3]:,.0f}<extra></extra>"
        ),
    ))
    apply_theme(fig, "Bitcoin Rainbow (Log Regression Bands)", height=380)
    if log_scale:
        fig.update_yaxes(type="log")
    return fig


def build_rotation_ladder_chart(ladder_ratios_df: pd.DataFrame) -> go.Figure | None:
    """Rotation ladder: z-score normalized ratios (ETH/BTC, BTC/SPY, SPY/GLD, GLD/TLT) for Tab 3."""
    if ladder_ratios_df.empty or len(ladder_ratios_df.columns) == 0:
        return None
    zscore_df = prepare_rotation_zscore(ladder_ratios_df, window=None)
    if zscore_df.empty:
        return None
    return build_curves_chart(zscore_df, title="Rotation Ladder (z-score normalized ratios)")


def build_all_charts(
    val_df: pd.DataFrame,
    risk_df: pd.DataFrame,
    yield_df: pd.DataFrame,
    liquidity_df: pd.DataFrame,
    rot_df: pd.DataFrame,
    overlay_valuation: pd.Series | None = None,
    overlay_risk: pd.Series | None = None,
    show_10y_3m: bool = False,
    show_event_markers: bool = False,
    use_fred_only_last: bool = False,
):
    """Return (fig_liquidity, fig_valuation, fig_macro_risk, fig_yield, fig_fci, fig_credit, fig_thermo, fig_last). Any can be None."""
    if use_fred_only_last or rot_df.empty:
        regime_curves = prepare_regime_curves(val_df, risk_df)
        fig_last = build_curves_chart(regime_curves, title="Macro Regime (FRED) — 100 = start")
    else:
        fig_last = build_rotation_chart(rot_df)
    return (
        build_liquidity_chart(liquidity_df, show_event_markers=show_event_markers),
        build_valuation_chart(val_df, overlay_series=overlay_valuation, show_event_markers=show_event_markers),
        build_macro_risk_chart(risk_df, overlay_series=overlay_risk, show_event_markers=show_event_markers),
        build_yield_curve_chart(yield_df, show_10y_3m_lines=show_10y_3m, show_event_markers=show_event_markers),
        build_fci_chart(risk_df, show_ma=True, show_event_markers=show_event_markers),
        build_credit_spreads_chart(risk_df, show_event_markers=show_event_markers),
        build_thermostat_chart(risk_df, overlay_series=overlay_risk, show_event_markers=show_event_markers),
        fig_last,
    )
