"""
Export Plotly figures to PNG. Tries Kaleido first (pip only, no Chromium).
Falls back to Playwright if Kaleido isn't available or fails.
"""
from __future__ import annotations

import io
import json
from typing import Any

# Plotly.js CDN (stable) — used only for Playwright fallback
PLOTLY_JS = "https://cdn.plot.ly/plotly-2.27.0.min.js"


def _try_kaleido(fig: Any, width: int, height: int) -> bytes | None:
    """Use Kaleido if installed (no Chromium). Returns PNG bytes or None."""
    if fig is None:
        return None
    try:
        buf = io.BytesIO()
        fig.write_image(buf, format="png", width=width, height=height)
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        return None


def _json_serializable(obj: Any) -> Any:
    """Convert numpy types and nested structures so json.dumps works."""
    try:
        import numpy as np
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {k: _json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_serializable(v) for v in obj]
    return obj


def _try_playwright(fig: Any, width: int, height: int) -> bytes | None:
    """Use Playwright + Chromium. Returns PNG bytes or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        fig_dict = fig.to_dict()
    except Exception:
        return None
    data = _json_serializable(fig_dict.get("data", []))
    layout_dict = _json_serializable(fig_dict.get("layout", {}))
    layout_dict["width"] = width
    layout_dict["height"] = height
    layout_dict["autosize"] = False
    figure_json = json.dumps({"data": data, "layout": layout_dict})
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <script src="{PLOTLY_JS}"></script>
</head>
<body style="margin:0;background:white;">
  <div id="chart" style="width:{width}px;height:{height}px;"></div>
  <script>
    var figure = {figure_json};
    Plotly.newPlot('chart', figure.data, figure.layout, {{responsive: false, staticPlot: false}});
  </script>
</body>
</html>"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width + 20, "height": height + 20})
            page.set_content(html, wait_until="networkidle")
            page.wait_for_timeout(800)
            chart = page.locator("#chart")
            png_bytes = chart.screenshot(type="png")
            browser.close()
        return png_bytes
    except Exception:
        return None


def export_plotly_to_png(
    fig: Any,
    *,
    width: int = 800,
    height: int = 450,
    scale: float = 2,
) -> bytes | None:
    """
    Export Plotly figure to PNG. Tries Kaleido first (pip only), then Playwright.
    """
    if fig is None:
        return None
    layout = getattr(fig, "layout", None)
    w, h = width, height
    if layout is not None:
        lw = getattr(layout, "width", None)
        lh = getattr(layout, "height", None)
        if lw is not None:
            w = int(lw)
        if lh is not None:
            h = int(lh)
    out = _try_kaleido(fig, w, h)
    if out is not None:
        return out
    return _try_playwright(fig, w, h)


def export_plotly_to_png_or_error(
    fig: Any,
    *,
    width: int = 800,
    height: int = 450,
) -> tuple[bytes | None, str | None]:
    """
    Export Plotly figure to PNG. Returns (png_bytes, None) or (None, error_message).
    Tries Kaleido first (pip only); no Chromium needed if Kaleido works.
    """
    if fig is None:
        return None, "No figure"
    try:
        out = export_plotly_to_png(fig, width=width, height=height, scale=1)
    except Exception as e:
        return None, str(e).strip() or "Chart export failed"
    if out is not None:
        return out, None
    return None, "Charts need Kaleido or Playwright. Install Kaleido (no Chromium): pip install kaleido"
