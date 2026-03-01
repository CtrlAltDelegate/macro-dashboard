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


def build_valuation_chart(val_df: pd.DataFrame) -> go.Figure | None:
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
        name="Valuation Pressure (rebased)", line=dict(color="#58a6ff", width=2)
    ))
    apply_theme(fig, "Valuation Pressure Index (rebased to 100)", height=380)
    return fig


def build_macro_risk_chart(risk_df: pd.DataFrame) -> go.Figure | None:
    if risk_df.empty or len(risk_df) < 60:
        return None
    raw = compute_macro_risk_composite(risk_df)
    roc = compute_macro_risk_roc(raw, period=21)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=raw.index, y=raw.values, mode="lines", name="Raw composite", line=dict(color="#58a6ff", width=2)))
    fig.add_trace(go.Scatter(x=roc.index, y=roc.values, mode="lines", name="ROC (21-period)", line=dict(color="#d29922", width=1.5)))
    apply_theme(fig, "Macro Risk — Raw & ROC", height=380)
    return fig


def build_thermostat_chart(risk_df: pd.DataFrame) -> go.Figure | None:
    if risk_df.empty or len(risk_df) < 60:
        return None
    raw = compute_macro_risk_composite(risk_df)
    thermo = compute_risk_thermostat(raw)
    if thermo.empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=thermo.index, y=thermo.values, mode="lines", name="Thermostat", line=dict(color="#58a6ff", width=2)))
    fig.add_hline(y=25, line_dash="dot", line_color="#3fb950")
    fig.add_hline(y=50, line_dash="dot", line_color="#8b949e")
    fig.add_hline(y=70, line_dash="dot", line_color="#d29922")
    fig.add_hline(y=85, line_dash="dot", line_color="#f85149")
    apply_theme(fig, "Risk Thermostat", height=380)
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


def build_all_charts(val_df: pd.DataFrame, risk_df: pd.DataFrame, rot_df: pd.DataFrame):
    """Return (fig1, fig2, fig3, fig4) for valuation, macro risk, thermostat, rotation. Any can be None."""
    return (
        build_valuation_chart(val_df),
        build_macro_risk_chart(risk_df),
        build_thermostat_chart(risk_df),
        build_rotation_chart(rot_df),
    )
