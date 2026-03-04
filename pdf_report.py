"""
Build a single PDF of the Macro Dashboard for download, email, or print.
Uses reportlab; chart images are PNG bytes from Plotly export.
"""
from __future__ import annotations

import io
from datetime import date
from typing import List, Tuple

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer
    from reportlab.lib.enums import TA_LEFT
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False

# Page width for chart images (leave margins)
CHART_WIDTH = 5.5 * inch  # ~396 pt
MAX_CHART_HEIGHT = 3.2 * inch


def build_dashboard_pdf(
    sections: List[Tuple[str, str, bytes | None]],
    report_date: str | None = None,
    readout_text: str | None = None,
) -> bytes:
    """
    Build a PDF with title, optional readout summary, and one section per chart.
    Each section: (title, description_plain_text, png_bytes or None).
    Returns PDF file as bytes.
    """
    if not _REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is required for PDF export. Install with: pip install reportlab")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="DashboardTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=6,
        textColor=colors.HexColor("#1a1a1a"),
    )
    heading_style = ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=14,
        spaceAfter=4,
        textColor=colors.HexColor("#333333"),
    )
    body_style = ParagraphStyle(
        name="SectionBody",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=8,
        textColor=colors.HexColor("#444444"),
        alignment=TA_LEFT,
    )
    placeholder_style = ParagraphStyle(
        name="Placeholder",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=12,
        textColor=colors.grey,
        fontName="Helvetica-Oblique",
    )

    story = []

    # Title and date
    report_date = report_date or date.today().isoformat()
    story.append(Paragraph("Macro Dashboard", title_style))
    story.append(Paragraph(f"Report date: {report_date}", body_style))
    story.append(Spacer(1, 0.2 * inch))

    if readout_text and readout_text.strip():
        story.append(Paragraph("Current readout", heading_style))
        story.append(Paragraph(readout_text.replace("\n", "<br/>"), body_style))
        story.append(Spacer(1, 0.15 * inch))

    for title, description, png_bytes in sections:
        story.append(Paragraph(title, heading_style))
        story.append(Paragraph(description, body_style))
        if png_bytes:
            try:
                img = Image(io.BytesIO(png_bytes), width=CHART_WIDTH)
                # Keep aspect ratio; cap height for readability
                if getattr(img, "imageHeight", None) and getattr(img, "imageWidth", None):
                    r = img.imageHeight / img.imageWidth
                    h = CHART_WIDTH * r
                    if h > MAX_CHART_HEIGHT:
                        img.drawHeight = MAX_CHART_HEIGHT
                        img.drawWidth = MAX_CHART_HEIGHT / r
                    else:
                        img.drawHeight = h
                        img.drawWidth = CHART_WIDTH
                story.append(img)
            except Exception:
                story.append(Paragraph("[Chart image could not be embedded.]", placeholder_style))
        else:
            story.append(Paragraph("[Chart not available for this period.]", placeholder_style))
        story.append(Spacer(1, 0.15 * inch))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def pdf_available() -> bool:
    """Return True if reportlab is installed and PDF export can be used."""
    return _REPORTLAB_AVAILABLE
