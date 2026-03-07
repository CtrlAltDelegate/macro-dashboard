"""
Build a single PDF of the Macro Dashboard for download, email, or print.
Uses reportlab; chart images are exported from Plotly figures at build time (or pre-supplied PNG bytes).
Supports: Executive Summary + Macro Radar on Page 1, then all chart sections from all three tabs.
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any, Callable, List, TypedDict

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    _REPORTLAB_AVAILABLE = True
    # Page and chart dimensions (require inch)
    _PAGE_CONTENT_WIDTH = 7.0 * inch
    _CHART_WIDTH = 6.2 * inch
    _MAX_CHART_HEIGHT = 4.0 * inch
    _RADAR_SIZE = 3.8 * inch
    # Professional macro briefing theme
    _REPORT_TITLE_C = colors.HexColor("#e6edf3")
    _REPORT_DATE_C = colors.HexColor("#8b949e")
    _REPORT_HEADING_C = colors.HexColor("#252525")
    _BODY_TEXT_C = colors.HexColor("#333333")
    _READOUT_BG = colors.HexColor("#21262d")
    _READOUT_BORDER = colors.HexColor("#30363d")
    _RULE_COLOR = colors.HexColor("#30363d")
    _PLACEHOLDER_COLOR = colors.HexColor("#888888")
    _NEUTRAL_C = colors.HexColor("#8b949e")
except ImportError:
    _REPORTLAB_AVAILABLE = False
    _PAGE_CONTENT_WIDTH = _CHART_WIDTH = _MAX_CHART_HEIGHT = _RADAR_SIZE = None
    _REPORT_TITLE_C = _REPORT_DATE_C = _REPORT_HEADING_C = _BODY_TEXT_C = None
    _READOUT_BG = _READOUT_BORDER = _RULE_COLOR = _PLACEHOLDER_COLOR = _NEUTRAL_C = None

# Public constants for layout (used only when reportlab is available)
PAGE_CONTENT_WIDTH = _PAGE_CONTENT_WIDTH or 504  # fallback points
CHART_WIDTH = _CHART_WIDTH or 446
MAX_CHART_HEIGHT = _MAX_CHART_HEIGHT or 288
RADAR_SIZE = _RADAR_SIZE or 274
REPORT_TITLE = _REPORT_TITLE_C
REPORT_DATE = _REPORT_DATE_C
REPORT_HEADING = _REPORT_HEADING_C
BODY_TEXT = _BODY_TEXT_C
READOUT_BG = _READOUT_BG
READOUT_BORDER = _READOUT_BORDER
RULE_COLOR = _RULE_COLOR
PLACEHOLDER_COLOR = _PLACEHOLDER_COLOR
NEUTRAL = _NEUTRAL_C


class SnapshotDict(TypedDict, total=False):
    """Today's Snapshot metrics for Page 1."""
    macro_score: str
    zone_label: str
    liquidity_status: str
    yield_status: str
    spread_val: str
    credit_status: str
    fci_status: str


class SummarySection(TypedDict, total=False):
    type: str  # "summary"
    title: str
    report_date: str
    lookback_label: str
    data_sources: str
    snapshot: SnapshotDict
    radar_png_bytes: bytes | None


class ChartSection(TypedDict, total=False):
    type: str  # "chart"
    title: str
    caption: str
    fig: Any  # Plotly figure or PNG bytes


SectionDict = SummarySection | ChartSection


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


def _add_snapshot_table(
    story: list,
    snapshot: SnapshotDict,
    snapshot_heading_style: Any,
    snapshot_label_style: Any,
    snapshot_value_style: Any,
) -> None:
    """Append Today's Snapshot card (dark-style) to story."""
    rows = []
    if snapshot.get("macro_score") and snapshot.get("zone_label"):
        rows.append(["Market Risk Score", f"{snapshot['macro_score']} — {snapshot['zone_label']}"])
    if snapshot.get("liquidity_status"):
        rows.append(["Liquidity", snapshot["liquidity_status"]])
    if snapshot.get("yield_status") and snapshot.get("spread_val"):
        rows.append(["Yield Curve (10Y–3M)", f"{snapshot['spread_val']} — {snapshot['yield_status']}"])
    if snapshot.get("credit_status"):
        rows.append(["Credit Stress (HY OAS)", snapshot["credit_status"]])
    if snapshot.get("fci_status"):
        rows.append(["Financial Conditions (NFCI)", snapshot["fci_status"]])
    if not rows:
        return
    from reportlab.lib.units import inch
    col0_w = 1.8 * inch
    col1_w = PAGE_CONTENT_WIDTH - col0_w - 24  # padding
    table_data = [
        [Paragraph(f"<b>{r[0]}</b>", snapshot_label_style), Paragraph(r[1], snapshot_value_style)]
        for r in rows
    ]
    tbl = Table(table_data, colWidths=[col0_w, col1_w])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), READOUT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, READOUT_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(Paragraph("Today's Snapshot", snapshot_heading_style))
    story.append(tbl)
    story.append(Spacer(1, 0.2 * inch))


def build_dashboard_pdf(
    sections: List[SectionDict],
    report_date: str | None = None,
    lookback_label: str = "5y",
    data_sources: str = "FRED, Yahoo Finance",
    export_fn: Callable[[Any], bytes | None] | None = None,
) -> bytes:
    """
    Build a single PDF report with:
      - Page 1: Executive header ("Macro Intelligence Brief"), date/lookback/sources,
                Today's Snapshot card, Macro Radar (spider chart) image.
      - Following pages: Numbered chart sections (title + caption + image) for all tabs.

    sections: list of dicts. First may be type "summary" with keys:
      title, report_date?, lookback_label?, data_sources?, snapshot (dict), radar_png_bytes? (or radar_fig; export_fn used).
    Remaining items: type "chart" with title, caption, fig (or pre-exported PNG via export_fn).

    If first section is summary, it may include radar_fig (Plotly figure) and export_fn will be used
    to get PNG bytes for the radar. Alternatively pass radar_png_bytes directly after export.
    """
    if not _REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is required for PDF export. Install with: pip install reportlab")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.55 * inch,
    )
    styles = getSampleStyleSheet()

    # Executive header (dark bar style via table)
    title_style = ParagraphStyle(
        name="ReportTitle",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=REPORT_TITLE,
        spaceAfter=2,
        spaceBefore=0,
        alignment=TA_LEFT,
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        name="ReportSubtitle",
        parent=styles["Normal"],
        fontSize=9,
        textColor=REPORT_DATE,
        spaceAfter=10,
        spaceBefore=0,
        alignment=TA_LEFT,
    )
    # Section heading for chart blocks
    heading_style = ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=16,
        spaceAfter=6,
        textColor=REPORT_HEADING,
        fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        name="SectionBody",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=10,
        textColor=BODY_TEXT,
        alignment=TA_LEFT,
        leading=13,
    )
    snapshot_heading_style = ParagraphStyle(
        name="SnapshotHeading",
        parent=styles["Normal"],
        fontSize=10,
        textColor=REPORT_HEADING,
        spaceAfter=6,
        spaceBefore=0,
        fontName="Helvetica-Bold",
    )
    snapshot_label_style = ParagraphStyle(
        name="SnapshotLabel",
        parent=styles["Normal"],
        fontSize=9,
        textColor=NEUTRAL,
    )
    snapshot_value_style = ParagraphStyle(
        name="SnapshotValue",
        parent=styles["Normal"],
        fontSize=9,
        textColor=BODY_TEXT,
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

    # Resolve report date and first section
    report_date_str = report_date or date.today().isoformat()
    dt_display = datetime.now().strftime("%Y-%m-%d %H:%M") if not report_date else report_date_str

    first = sections[0] if sections else {}
    if first.get("type") == "summary":
        # Page 1: Executive header
        story.append(Paragraph("Macro Intelligence Brief", title_style))
        lookback = first.get("lookback_label") or lookback_label
        sources = first.get("data_sources") or data_sources
        story.append(Paragraph(
            f"Report date: {report_date_str} · Lookback: {lookback} · Data: {sources}",
            subtitle_style,
        ))
        rule_table = Table([[""]], colWidths=[PAGE_CONTENT_WIDTH], rowHeights=[2])
        rule_table.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1, RULE_COLOR)]))
        story.append(rule_table)
        story.append(Spacer(1, 0.25 * inch))

        snapshot = first.get("snapshot") or {}
        _add_snapshot_table(
            story, snapshot,
            snapshot_heading_style, snapshot_label_style, snapshot_value_style,
        )

        # Macro Radar image
        radar_bytes = first.get("radar_png_bytes")
        if radar_bytes is None and export_fn and first.get("radar_fig") is not None:
            radar_bytes = _get_png_bytes(first["radar_fig"], export_fn)
        if radar_bytes:
            try:
                rad_img = Image(io.BytesIO(radar_bytes), width=RADAR_SIZE, height=RADAR_SIZE)
                story.append(Paragraph("Macro Radar — Risk by pillar (0–100, higher = worse)", snapshot_heading_style))
                story.append(rad_img)
            except Exception:
                story.append(Paragraph("[Macro Radar chart could not be embedded.]", placeholder_style))
        story.append(Spacer(1, 0.3 * inch))

        chart_sections = sections[1:]
    else:
        # No summary section: simple title + date
        story.append(Paragraph("Macro Intelligence Brief", title_style))
        story.append(Paragraph(f"Report date: {report_date_str} · Lookback: {lookback_label}", subtitle_style))
        rule_table = Table([[""]], colWidths=[PAGE_CONTENT_WIDTH], rowHeights=[2])
        rule_table.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1, RULE_COLOR)]))
        story.append(rule_table)
        story.append(Spacer(1, 0.2 * inch))
        chart_sections = sections

    # Chart sections (numbered)
    for idx, sec in enumerate(chart_sections, start=1):
        if sec.get("type") != "chart":
            continue
        title = sec.get("title") or f"Section {idx}"
        caption = sec.get("caption") or ""
        content = sec.get("fig")
        if title and not title.strip().startswith(str(idx)):
            title = f"{idx}. {title}"
        story.append(Paragraph(title, heading_style))
        if caption:
            story.append(Paragraph(caption.replace("\n", "<br/>").replace("&", "&amp;"), body_style))
        png_bytes = _get_png_bytes(content, export_fn)
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
            story.append(Paragraph(
                "[Chart could not be embedded. Run the app locally with kaleido for PDFs with charts.]",
                placeholder_style,
            ))
        story.append(Spacer(1, 0.2 * inch))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def pdf_available() -> bool:
    """Return True if reportlab is installed and PDF export can be used."""
    return _REPORTLAB_AVAILABLE
