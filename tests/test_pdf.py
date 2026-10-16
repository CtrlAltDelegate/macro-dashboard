import io

from PIL import Image
from pypdf import PdfReader

from pdf_report import build_dashboard_pdf


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 450), "white").save(buf, format="PNG")
    return buf.getvalue()


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def test_pdf_has_snapshot_changes_and_charts():
    summary = {
        "type": "summary",
        "snapshot": {"macro_score": "41/100", "zone_label": "Moderate Risk",
                     "extra": [("Net Liquidity", "$6.01T"), ("Sahm Rule", "0.27 (recession signal at 0.50)")]},
        "changes_since": "Tue Oct 13",
        "changes": [
            {"signal": "HY OAS", "now": "4.25%", "change": "+12bp", "size_vs_typical": "large", "direction": "riskier"},
            {"signal": "S&P 500", "now": "6,600", "change": "+1.2%", "direction": "safer"},
        ],
    }
    charts = [
        {"type": "chart", "title": "Net Liquidity", "caption": "Fed balance sheet minus TGA & RRP.", "fig": _png()},
        {"type": "chart", "title": "Economic Risk Index", "caption": "Six pillars.", "fig": object()},  # export fails
    ]
    text = _text(build_dashboard_pdf([summary] + charts, report_date="2026-10-16", export_fn=lambda fig: None))
    assert "What changed since Tue Oct 13" in text
    assert "HY OAS" in text and "+12bp" in text and "riskier" in text
    assert "Net Liquidity" in text and "Sahm Rule" in text
    assert "1. Net Liquidity" in text and "2. Economic Risk Index" in text
    assert "PNG export (Kaleido) is unavailable" in text          # failed chart noted, PDF still built
    assert "playwright" not in text.lower()


def test_pdf_without_changes_or_charts_still_builds():
    text = _text(build_dashboard_pdf([{"type": "summary", "snapshot": {}}], report_date="2026-10-16"))
    assert "Macro Intelligence Brief" in text and "What changed" not in text
