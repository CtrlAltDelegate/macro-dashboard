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
)

# Risk band thresholds and labels (0–100 scale)
THERMO_BANDS = [(0, 20, "Very Low Risk"), (20, 40, "Low Risk"), (40, 60, "Moderate Risk"), (60, 80, "High Risk"), (80, 100, "Extreme Risk")]
THERMO_HLINES = [20, 40, 60, 80]

OVERLAY_COLOR = "rgba(140, 140, 140, 0.65)"
OVERLAY_LINE = dict(color=OVERLAY_COLOR, width=1.2, dash="dash")


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


def build_valuation_chart(val_df: pd.DataFrame, overlay_series: pd.Series | None = None) -> go.Figure | None:
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
    apply_theme(fig, "Stock Market Pressure (rebased to 100)", height=380)
    return fig


def build_macro_risk_chart(risk_df: pd.DataFrame, overlay_series: pd.Series | None = None) -> go.Figure | None:
    if risk_df.empty or len(risk_df) < 60:
        return None
    raw = compute_macro_risk_composite(risk_df)
    roc = compute_macro_risk_roc(raw, period=21)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=raw.index, y=raw.values, mode="lines", name="Raw composite", line=dict(color="#58a6ff", width=2)))
    fig.add_trace(go.Scatter(x=roc.index, y=roc.values, mode="lines", name="ROC (21-period)", line=dict(color="#d29922", width=1.5)))
    _add_market_overlay(fig, overlay_series, use_secondary_y=True)
    apply_theme(fig, "Economic Risk Index — Raw & ROC", height=380)
    return fig


def build_thermostat_chart(risk_df: pd.DataFrame, overlay_series: pd.Series | None = None) -> go.Figure | None:
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
    apply_theme(fig, "Market Risk Level (0–100)", height=380)
    fig.update_yaxes(range=[0, 100])
    return fig


def build_rotation_chart(rot_df: pd.DataFrame) -> go.Figure | None:
    if rot_df.empty:
        return None
    curves = prepare_rotation_curves(rot_df)
    if curves.empty:
        return None
    fig = go.Figure()
    colors = ["#f85149", "#d29922", "#58a6ff", "#a371f7", "#3fb950"]
    for i, col in enumerate(curves.columns):
        fig.add_trace(go.Scatter(
            x=curves.index, y=curves[col].values, mode="lines",
            name=col, line=dict(color=colors[i % len(colors)], width=1.5)
        ))
    apply_theme(fig, "Rotation — Relative strength (100 = start)", height=400)
    return fig


def build_all_charts(
    val_df: pd.DataFrame,
    risk_df: pd.DataFrame,
    rot_df: pd.DataFrame,
    overlay_valuation: pd.Series | None = None,
    overlay_risk: pd.Series | None = None,
):
    """Return (fig1, fig2, fig3, fig4) for valuation, macro risk, thermostat, rotation. Any can be None."""
    return (
        build_valuation_chart(val_df, overlay_series=overlay_valuation),
        build_macro_risk_chart(risk_df, overlay_series=overlay_risk),
        build_thermostat_chart(risk_df, overlay_series=overlay_risk),
        build_rotation_chart(rot_df),
    )
