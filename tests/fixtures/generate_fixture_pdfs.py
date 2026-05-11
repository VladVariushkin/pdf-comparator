"""
Generate two fixture PDFs for testing split-table detection:

  table_split.pdf   – "Channel Performance Metrics" table is too tall (large font)
                       and flows across two pages.
  table_single.pdf  – Same table name and columns, but smaller font / fewer rows
                       so everything fits on one page.
"""

from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

OUT = Path(__file__).parent
styles = getSampleStyleSheet()
H1 = styles["Heading1"]
H2 = styles["Heading2"]
BODY = styles["BodyText"]


def _doc(filename, **kw):
    return SimpleDocTemplate(
        str(OUT / filename),
        pagesize=LETTER,
        leftMargin=inch, rightMargin=inch,
        topMargin=inch, bottomMargin=inch,
        **kw,
    )


def _tbl(data, col_widths=None, font_size=9):
    t = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1a3c5e")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  font_size + 1),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#eaf1f8")]),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), font_size),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#b0c4d8")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    return t


# ---------------------------------------------------------------------------
# Shared table data
# ---------------------------------------------------------------------------
TABLE_TITLE = "Channel Performance Metrics"

HEADER = ["Channel", "Region", "Viewers (M)", "Avg Watch (min)", "Peak Hour", "Ad Fill Rate"]

# 30 rows — with a large font this will overflow onto page 2;
# with the compact font used in the single-page PDF it fits on one page.
ROWS = [
    ["NBC East",         "Northeast",    "4.21",  "38",  "20:00", "94 %"],
    ["NBC West",         "West Coast",   "3.87",  "41",  "21:00", "92 %"],
    ["MSNBC",            "National",     "2.15",  "55",  "19:00", "88 %"],
    ["CNBC",             "National",     "1.93",  "48",  "09:00", "91 %"],
    ["USA Network",      "National",     "1.74",  "32",  "21:00", "89 %"],
    ["Bravo",            "National",     "1.41",  "29",  "21:00", "87 %"],
    ["E! Entertainment", "National",     "1.22",  "26",  "22:00", "85 %"],
    ["Oxygen",           "National",     "0.98",  "44",  "20:00", "83 %"],
    ["Syfy",             "National",     "0.87",  "61",  "21:00", "86 %"],
    ["NBC Sports",       "National",     "3.10",  "72",  "15:00", "96 %"],
    ["Golf Channel",     "National",     "0.45",  "90",  "13:00", "90 %"],
    ["Peacock Free",     "Digital",      "5.60",  "24",  "20:00", "78 %"],
    ["Peacock Premium",  "Digital",      "3.30",  "52",  "21:00", "95 %"],
    ["Telemundo East",   "Northeast",    "1.88",  "33",  "20:00", "82 %"],
    ["Telemundo West",   "West Coast",   "1.65",  "35",  "21:00", "81 %"],
    ["NBC Chicago",      "Midwest",      "2.44",  "36",  "22:00", "93 %"],
    ["NBC Dallas",       "South",        "2.01",  "37",  "21:00", "91 %"],
    ["NBC Miami",        "South",        "1.77",  "34",  "20:00", "89 %"],
    ["NBC Atlanta",      "South",        "1.65",  "39",  "20:00", "88 %"],
    ["NBC Denver",       "Mountain",     "1.02",  "42",  "20:00", "87 %"],
    ["NBC Phoenix",      "Southwest",    "1.14",  "40",  "19:00", "86 %"],
    ["NBC Seattle",      "Pacific NW",   "1.33",  "43",  "20:00", "90 %"],
    ["NBC Portland",     "Pacific NW",   "0.89",  "41",  "20:00", "85 %"],
    ["NBC San Diego",    "West Coast",   "0.95",  "38",  "21:00", "84 %"],
    ["NBC Sacramento",   "West Coast",   "0.78",  "36",  "21:00", "83 %"],
    ["NBC Boston",       "Northeast",    "2.12",  "40",  "22:00", "92 %"],
    ["NBC Philadelphia", "Northeast",    "2.33",  "38",  "22:00", "91 %"],
    ["NBC Washington",   "Mid-Atlantic", "2.55",  "37",  "21:00", "93 %"],
    ["NBC Detroit",      "Midwest",      "1.50",  "35",  "20:00", "88 %"],
    ["NBC Minneapolis",  "Midwest",      "1.28",  "36",  "20:00", "87 %"],
]


# ---------------------------------------------------------------------------
# PDF 1 – table split across two pages (large font forces overflow)
# ---------------------------------------------------------------------------
def build_split():
    large_h2 = ParagraphStyle(
        "LargeH2", parent=H2, fontSize=16, spaceAfter=10
    )
    story = [
        Paragraph("NBCUniversal Q1 2025 — Viewership Report (Draft A)", H1),
        Spacer(1, 0.1 * inch),
        Paragraph(TABLE_TITLE, large_h2),
        _tbl([HEADER] + ROWS,
             col_widths=[1.5*inch, 1.1*inch, 1.0*inch, 1.2*inch, 0.85*inch, 0.9*inch],
             font_size=13),   # large font → table won't fit on one page
    ]
    _doc("table_split.pdf").build(story)
    print("  table_split.pdf  (table spans 2 pages)")


# ---------------------------------------------------------------------------
# PDF 2 – same table name, fewer rows, fits on one page
# The first 18 rows fit comfortably on a single letter page at font size 9.
# ---------------------------------------------------------------------------
def build_single():
    story = [
        Paragraph("NBCUniversal Q1 2025 — Viewership Report (Draft B)", H1),
        Spacer(1, 0.1 * inch),
        Paragraph(TABLE_TITLE, H2),
        _tbl([HEADER] + ROWS[:18],
             col_widths=[1.5*inch, 1.1*inch, 1.0*inch, 1.2*inch, 0.85*inch, 0.9*inch],
             font_size=9),    # standard font, fewer rows → all fits on one page
    ]
    _doc("table_single.pdf").build(story)
    print("  table_single.pdf (table fits on 1 page)")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Writing fixture PDFs to {OUT}/")
    build_split()
    build_single()
    print("Done.")
