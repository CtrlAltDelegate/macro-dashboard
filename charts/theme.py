"""
Institutional, minimal chart theme for newsletter-ready PNG export.
Readable on mobile (Substack); clean and professional.
"""
from __future__ import annotations

import plotly.graph_objects as go


# Neutral, high-contrast palette
BACKGROUND = "#0d1117"
GRID = "#30363d"
TEXT = "#e6edf3"
AXIS_LIGHT = "#8b949e"
ACCENT = "#58a6ff"
ACCENT_ALT = "#3fb950"
ACCENT_WARN = "#d29922"
ACCENT_RISK = "#f85149"

FONT_FAMILY = "Inter, system-ui, -apple-system, sans-serif"
FONT_SIZE = 13
TITLE_SIZE = 16


def apply_theme(fig: go.Figure, title: str, height: int = 420) -> go.Figure:
    """Apply minimal institutional theme; good for PNG export and mobile."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=TITLE_SIZE, color=TEXT), x=0.02, xanchor="left"),
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        font=dict(family=FONT_FAMILY, size=FONT_SIZE, color=TEXT),
        margin=dict(l=56, r=32, t=48, b=48),
        height=height,
        hovermode="x unified",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor=GRID,
            zeroline=False,
            linecolor=AXIS_LIGHT,
            tickfont=dict(color=AXIS_LIGHT, size=11),
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=GRID,
            zeroline=False,
            linecolor=AXIS_LIGHT,
            tickfont=dict(color=AXIS_LIGHT, size=11),
            showspikes=True,
        ),
    )
    return fig
