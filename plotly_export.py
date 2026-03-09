"""
Export Plotly figures to PNG using Playwright (no Kaleido).
Run once: playwright install chromium
"""
from __future__ import annotations

import json
from typing import Any

# Plotly.js CDN (stable)
PLOTLY_JS = "https://cdn.plot.ly/plotly-2.27.0.min.js"


def export_plotly_to_png(
    fig: Any,
    *,
    width: int = 800,
    height: int = 450,
    scale: float = 2,
) -> bytes | None:
    """
    Export a Plotly figure to PNG bytes using headless Chromium via Playwright.
    Returns None if Playwright is not installed or export fails.
    """
    if fig is None:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    layout = getattr(fig, "layout", None)
    if layout is not None:
        w = getattr(layout, "width", None)
        h = getattr(layout, "height", None)
        if w is not None:
            width = int(w)
        if h is not None:
            height = int(h)

    # Serialize figure for Plotly.js (fig.to_dict() gives {data, layout})
    try:
        fig_dict = fig.to_dict()
    except Exception:
        return None
    data = fig_dict.get("data", [])
    layout_dict = fig_dict.get("layout", {})
    layout_dict["width"] = width
    layout_dict["height"] = height
    # Avoid responsive sizing so dimensions are exact
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


def export_plotly_to_png_or_error(
    fig: Any,
    *,
    width: int = 800,
    height: int = 450,
) -> tuple[bytes | None, str | None]:
    """
    Export Plotly figure to PNG. Returns (png_bytes, None) or (None, error_message).
    """
    if fig is None:
        return None, "No figure"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return (
            None,
            "Playwright not installed. Run: pip install playwright  then  python -m playwright install chromium",
        )
    try:
        out = export_plotly_to_png(fig, width=width, height=height, scale=1)
    except Exception as e:
        err = str(e).strip()
        if "Executable doesn't exist" in err or "chromium" in err.lower():
            return None, "Chromium not installed. Run: playwright install chromium"
        return None, err or "Playwright export failed"
    if out is not None:
        return out, None
    return None, "Export failed. Run: python -m playwright install chromium"
