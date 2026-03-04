"""
Build Plotly figures for all four dashboard charts. Shared by app.py and refresh.py.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .theme import apply_theme
from models import (
    compute_valuation_pressure_index,
    compute_macro_risk_composite,
    compute_macro_risk_roc,
    compute_risk_thermostat,
    prepare_rotation_curves,
    prepare_regime_curves,
)

# Risk band thresholds and labels (0–100 scale)
THERMO_BANDS = [(0, 20, "Very Low Risk"), (20, 40, "Low Risk"), (40, 60, "Moderate Risk"), (60, 80, "High Risk"), (80, 100, "Extreme Risk")]
THERMO_HLINES = [20, 40, 60, 80]

OVERLAY_COLOR = "rgba(140, 140, 140, 0.65)"
OVERLAY_LINE = dict(color=OVERLAY_COLOR, width=1.2, dash="dash")

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


def build_rotation_chart(rot_df: pd.DataFrame) -> go.Figure | None:
    """Build rotation chart from Yahoo ratio data. Returns None if empty."""
    if rot_df.empty:
        return None
    curves = prepare_rotation_curves(rot_df)
    return build_curves_chart(curves, title="Rotation — Relative strength (100 = start)")


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
