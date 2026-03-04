"""
Build a single PDF of the Macro Dashboard for download, email, or print.
Uses reportlab; chart images are exported from Plotly figures at build time (or pre-supplied PNG bytes).
"""
from __future__ import annotations

import io
from datetime import date
from typing import Any, Callable, List, Tuple

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib.enums import TA_LEFT
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False

# Page and chart dimensions
CHART_WIDTH = 5.5 * inch
MAX_CHART_HEIGHT = 3.2 * inch

# Theme (aligned with dashboard dark theme)
HEADER_BG = colors.HexColor("#0d1117")
HEADER_TEXT = colors.HexColor("#e6edf3")
READOUT_BG = colors.HexColor("#161b22")
READOUT_BORDER = colors.HexColor("#30363d")
BODY_TEXT = colors.HexColor("#1a1a1a")
SECTION_HEADING = colors.HexColor("#24292f")
MUTED = colors.HexColor("#57606a")
PLACEHOLDER_COLOR = colors.HexColor("#8b949e")


def _get_png_bytes(content: Any, export_fn: Callable[[Any], bytes | None] | None) -> bytes | None:
    """Return PNG bytes from content (bytes or Plotly figure). If figure, use export_fn."""
    if content is None:
        return None
    if isinstance(content, bytes):
        return content
    if export_fn and callable(export_fn):
        try:
            return export_fn(content)
        except Exception:
            return None
    return None


def build_dashboard_pdf(
    sections: List[Tuple[str, str, Any]],
    report_date: str | None = None,
    readout_text: str | None = None,
    export_fn: Callable[[Any], bytes | None] | None = None,
) -> bytes:
    """
    Build a PDF with title, optional readout summary, and one section per chart.
    Each section: (title, description_plain_text, png_bytes OR Plotly figure).
    If third element is a figure, export_fn(fig) is called to get PNG bytes.
    Returns PDF file as bytes.
    """
    if not _REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is required for PDF export. Install with: pip install reportlab")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.6 * inch,
    )
    styles = getSampleStyleSheet()

    # Title style for header bar
    title_style = ParagraphStyle(
        name="DashboardTitle",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=HEADER_TEXT,
        spaceAfter=0,
        spaceBefore=0,
        alignment=TA_LEFT,
        fontName="Helvetica-Bold",
    )
    date_style = ParagraphStyle(
        name="ReportDate",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#8b949e"),
        spaceAfter=0,
        spaceBefore=2,
        alignment=TA_LEFT,
    )
    heading_style = ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=16,
        spaceAfter=6,
        textColor=SECTION_HEADING,
        fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        name="SectionBody",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=10,
        textColor=BODY_TEXT,
        alignment=TA_LEFT,
        leading=12,
    )
    readout_style = ParagraphStyle(
        name="ReadoutText",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#e6edf3"),
        alignment=TA_LEFT,
        leading=12,
    )
    placeholder_style = ParagraphStyle(
        name="Placeholder",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=12,
        textColor=PLACEHOLDER_COLOR,
        fontName="Helvetica-Oblique",
    )

    story = []

    # Dark header bar
    report_date_str = report_date or date.today().isoformat()
    header_content = Paragraph("Macro Dashboard", title_style)
    date_para = Paragraph(f"Report date: {report_date_str}", date_style)
    header_table = Table([[header_content], [date_para]], colWidths=[6 * inch])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, READOUT_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.25 * inch))

    # Current readout box (dark panel)
    if readout_text and readout_text.strip():
        readout_heading = ParagraphStyle(
            name="ReadoutHeading",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#8b949e"),
            spaceAfter=6,
            fontName="Helvetica-Bold",
        )
        story.append(Paragraph("Current readout", readout_heading))
        readout_para = Paragraph(readout_text.replace("\n", "<br/>").replace("&", "&amp;"), readout_style)
        readout_table = Table([[readout_para]], colWidths=[6 * inch])
        readout_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), READOUT_BG),
            ("BOX", (0, 0), (-1, -1), 1, READOUT_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(readout_table)
        story.append(Spacer(1, 0.2 * inch))

    # Sections with charts
    for title, description, content in sections:
        png_bytes = _get_png_bytes(content, export_fn)
        story.append(Paragraph(title, heading_style))
        story.append(Paragraph(description, body_style))
        if png_bytes:
            try:
                img = Image(io.BytesIO(png_bytes), width=CHART_WIDTH)
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
