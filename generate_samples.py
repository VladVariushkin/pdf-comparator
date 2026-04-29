"""Generate 5 sample PDFs for doc-compare testing."""

from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

OUT = Path("samples")
OUT.mkdir(exist_ok=True)

styles = getSampleStyleSheet()
H1 = styles["Heading1"]
H2 = styles["Heading2"]
BODY = styles["BodyText"]
BODY.spaceAfter = 6


def doc(filename):
    return SimpleDocTemplate(
        str(OUT / filename),
        pagesize=LETTER,
        leftMargin=inch, rightMargin=inch,
        topMargin=inch, bottomMargin=inch,
    )


def tbl(data, col_widths=None):
    t = Table(data, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1a3c5e")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  10),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#eaf1f8")]),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 9),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#b0c4d8")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    return t


def hr():
    return HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#b0c4d8"), spaceAfter=8)


def p(text, style=None):
    return Paragraph(text, style or BODY)


def sp(h=0.15):
    return Spacer(1, h * inch)


# ---------------------------------------------------------------------------
# SAMPLE 1  --  Service Level Agreement (original)
# ---------------------------------------------------------------------------
def build_sample1():
    story = []
    story += [p("SERVICE LEVEL AGREEMENT", H1), hr()]
    story += [p(
        'This Service Level Agreement (the Agreement) is entered into as of January 15, 2025, '
        'between NBCUniversal Media, LLC (Client) and StreamTech Solutions, Inc. (Provider). '
        'This Agreement defines the service standards, performance metrics, and remediation '
        'procedures governing the video streaming infrastructure services provided to Client.'
    ), sp()]

    story += [p("1. Agreement Overview", H2)]
    story += [tbl([
        ["Field",               "Value"],
        ["Contract ID",         "SLA-2025-0042"],
        ["Effective Date",      "January 15, 2025"],
        ["Expiration Date",     "January 14, 2026"],
        ["Contract Value",      "$2,400,000 USD"],
        ["Billing Cycle",       "Monthly"],
        ["Governing Law",       "State of New York"],
        ["Dispute Resolution",  "Binding Arbitration - JAMS"],
    ], col_widths=[2.2*inch, 4.0*inch]), sp()]

    story += [p("2. Service Performance Targets", H2)]
    story += [tbl([
        ["Metric",                  "Target",    "Measurement Window", "Penalty Threshold"],
        ["Platform Uptime",         "99.95 %",   "Monthly",            "< 99.9 %"],
        ["Stream Start Time",       "<= 2.0 sec","Weekly avg.",         "> 3.0 sec"],
        ["Buffering Ratio",         "< 0.5 %",   "Weekly avg.",         "> 1.0 %"],
        ["Error Rate (5xx)",        "< 0.1 %",   "Daily avg.",          "> 0.3 %"],
        ["CDN Cache-Hit Ratio",     ">= 90 %",   "Daily avg.",          "< 85 %"],
        ["Support Response (P1)",   "<= 15 min", "Per incident",        "> 30 min"],
        ["Support Resolution (P1)", "<= 4 hrs",  "Per incident",        "> 8 hrs"],
    ], col_widths=[2.2*inch, 1.2*inch, 1.6*inch, 1.6*inch]), sp()]

    story += [p("3. Penalty and Credit Structure", H2)]
    story += [p(
        'In the event that Provider fails to meet any performance target defined in Section 2, '
        'Client shall be entitled to a Service Credit calculated as a percentage of the monthly '
        'fee for the affected service tier. Credits are applied to the following invoice and are '
        'non-transferable. Credits do not constitute a waiver of any other rights or remedies '
        'available to Client under this Agreement or applicable law.'
    )]
    story += [tbl([
        ["Severity", "Breach Duration", "Credit (% of Monthly Fee)"],
        ["Minor",    "< 1 hour",         "5 %"],
        ["Moderate", "1 - 4 hours",      "15 %"],
        ["Major",    "4 - 8 hours",      "30 %"],
        ["Critical", "> 8 hours",        "50 %"],
    ], col_widths=[1.5*inch, 2.0*inch, 3.0*inch]), sp()]

    story += [p("4. Maintenance Windows", H2)]
    story += [p(
        'Provider may conduct scheduled maintenance during the approved windows listed below '
        'without incurring SLA penalties, provided that Client receives no fewer than 72 hours '
        'of advance written notice. Emergency maintenance required to prevent imminent service '
        'degradation may be performed with 4 hours notice; any associated downtime will be '
        'excluded from uptime calculations for penalty purposes only.'
    )]
    story += [tbl([
        ["Window",    "Day(s)",        "Time (ET)",      "Max Duration"],
        ["Standard",  "Sunday",        "02:00 - 06:00",  "4 hours"],
        ["Extended",  "1st Sun/Month", "00:00 - 08:00",  "8 hours"],
        ["Emergency", "Any",           "As required",    "2 hours"],
    ], col_widths=[1.5*inch, 1.8*inch, 2.0*inch, 2.0*inch]), sp()]

    story += [p("5. Escalation Contacts", H2)]
    story += [tbl([
        ["Role",               "Name",         "Email",                     "Phone"],
        ["Account Manager",    "Sarah Kim",     "s.kim@streamtech.io",       "+1 212 555 0101"],
        ["Technical Lead",     "Marcus Webb",   "m.webb@streamtech.io",      "+1 212 555 0102"],
        ["Executive Sponsor",  "Diana Patel",   "d.patel@streamtech.io",     "+1 212 555 0103"],
        ["Client POC",         "James Ortega",  "j.ortega@nbcuniversal.com", "+1 212 664 0200"],
    ], col_widths=[1.5*inch, 1.5*inch, 2.4*inch, 1.4*inch]), sp()]

    doc("sample1_sla_original.pdf").build(story)
    print("  sample1_sla_original.pdf")


# ---------------------------------------------------------------------------
# SAMPLE 2  --  Technical Specification Report (original)
# ---------------------------------------------------------------------------
def build_sample2():
    story = []
    story += [p("STREAMING PLATFORM TECHNICAL SPECIFICATION", H1), hr()]
    story += [p(
        'This document provides the technical baseline specification for the NBCUniversal Peacock '
        'streaming platform encoding pipeline, Version 4.2. It covers codec profiles, packaging '
        'formats, CDN integration requirements, and quality-of-service targets. All figures are '
        'as-built values validated during the Q4 2024 performance audit unless otherwise noted.'
    ), sp()]

    story += [p("1. System Identification", H2)]
    story += [tbl([
        ["Parameter",       "Value"],
        ["System Name",     "Peacock Encoding Pipeline"],
        ["Version",         "4.2.1"],
        ["Release Date",    "November 8, 2024"],
        ["Owner",           "Platform Engineering - NBCU"],
        ["Classification",  "Internal / Confidential"],
        ["Review Cycle",    "Quarterly"],
        ["Last Audit Date", "December 18, 2024"],
    ], col_widths=[2.2*inch, 4.0*inch]), sp()]

    story += [p("2. Codec and Encoding Profiles", H2)]
    story += [tbl([
        ["Profile",   "Codec",  "Resolution", "Bitrate",  "Frame Rate", "HDR"],
        ["4K-HDR",    "HEVC",   "3840x2160",  "20 Mbps",  "60 fps",     "HDR10+"],
        ["1080p-HQ",  "AVC",    "1920x1080",  "8 Mbps",   "60 fps",     "SDR"],
        ["1080p-SD",  "AVC",    "1920x1080",  "4.5 Mbps", "30 fps",     "SDR"],
        ["720p",      "AVC",    "1280x720",   "2.5 Mbps", "30 fps",     "SDR"],
        ["480p",      "AVC",    "854x480",    "1.0 Mbps", "30 fps",     "SDR"],
        ["360p",      "AVC",    "640x360",    "0.5 Mbps", "30 fps",     "SDR"],
        ["Audio 5.1", "EAC3",   "N/A",        "640 kbps", "N/A",        "N/A"],
        ["Audio 2.0", "AAC-LC", "N/A",        "192 kbps", "N/A",        "N/A"],
    ], col_widths=[1.1*inch, 0.9*inch, 1.3*inch, 1.0*inch, 1.0*inch, 1.0*inch]), sp()]

    story += [p("3. Packaging and Delivery", H2)]
    story += [p(
        'Content is packaged in MPEG-DASH (ISO BMFF) with a 6-second segment duration and '
        'HLS (CMAF) with a 6-second segment duration for Apple device compatibility. '
        'DRM is enforced via Widevine (L1/L3), PlayReady (SL3000), and FairPlay. '
        'All manifests are generated by the Unified Packager v3.7 and distributed through '
        'the Akamai EdgeSuite CDN with an origin shield in Ashburn, VA.'
    )]
    story += [tbl([
        ["Format",        "Segment Duration", "DRM",                  "Target Device"],
        ["MPEG-DASH",     "6 seconds",        "Widevine / PlayReady", "Android, Web, CTV"],
        ["HLS (CMAF)",    "6 seconds",        "FairPlay",             "iOS, macOS, tvOS"],
        ["Smooth Stream", "4 seconds",        "PlayReady SL3000",     "Xbox, Windows"],
    ], col_widths=[1.4*inch, 1.5*inch, 2.0*inch, 2.0*inch]), sp()]

    story += [p("4. Infrastructure and Capacity", H2)]
    story += [tbl([
        ["Component",           "Specification",          "Count / Capacity"],
        ["Origin Servers",      "AWS EC2 c5.4xlarge",     "24 instances (auto-scale)"],
        ["Encoding Workers",    "AWS EC2 c5n.18xlarge",   "48 instances (spot fleet)"],
        ["Storage (hot tier)",  "AWS S3 Standard",        "2.4 PB allocated"],
        ["Storage (cold tier)", "AWS S3 Glacier IR",      "18 PB allocated"],
        ["Database (metadata)", "Aurora PostgreSQL 15.4", "Multi-AZ, r6g.4xlarge"],
        ["Message Queue",       "Apache Kafka 3.6",       "9-node cluster"],
        ["CDN PoP Coverage",    "Akamai EdgeSuite",       "142 PoPs globally"],
    ], col_widths=[2.0*inch, 2.4*inch, 2.3*inch]), sp()]

    story += [p("5. Quality Metrics (Q4 2024 Audit)", H2)]
    story += [tbl([
        ["Metric",                        "Measured Value", "Target",   "Status"],
        ["Encoding Completion Rate",      "99.87 %",        ">= 99.8 %","PASS"],
        ["Avg. Encoding Latency (4K)",    "4.2 min",        "<= 5 min", "PASS"],
        ["Avg. Encoding Latency (1080p)", "1.8 min",        "<= 3 min", "PASS"],
        ["Package Error Rate",            "0.03 %",         "< 0.1 %",  "PASS"],
        ["DRM License Issuance (p99)",    "210 ms",         "< 300 ms", "PASS"],
        ["CDN Origin Pull Error Rate",    "0.07 %",         "< 0.2 %",  "PASS"],
        ["VMAF Score (4K-HDR avg.)",      "93.2",           ">= 92",    "PASS"],
    ], col_widths=[2.5*inch, 1.5*inch, 1.2*inch, 1.0*inch]), sp()]

    doc("sample2_techspec_original.pdf").build(story)
    print("  sample2_techspec_original.pdf")


# ---------------------------------------------------------------------------
# SAMPLE 3  --  Master Vendor Services Contract (original)
# ---------------------------------------------------------------------------
def build_sample3():
    story = []
    story += [p("MASTER VENDOR SERVICES CONTRACT", H1), hr()]
    story += [p(
        'This Master Vendor Services Contract (the Contract) is executed as of March 1, 2025, '
        'by and between NBCUniversal Media, LLC, a Delaware limited liability company (NBCU), '
        'and CloudEdge Infrastructure Partners, LLC (Vendor). This Contract governs the '
        'procurement of cloud infrastructure, managed services, and professional services as '
        'further described in the attached Statement of Work (SOW-2025-CE-007).'
    ), sp()]

    story += [p("1. Contract Summary", H2)]
    story += [tbl([
        ["Field",               "Value"],
        ["Contract Number",     "MVSC-2025-CE-007"],
        ["SOW Reference",       "SOW-2025-CE-007"],
        ["Start Date",          "March 1, 2025"],
        ["End Date",            "February 28, 2027"],
        ["Total Contract Value","$5,750,000 USD"],
        ["Payment Terms",       "Net 30 days"],
        ["Currency",            "USD"],
        ["Auto-Renewal",        "Yes - 12-month terms"],
        ["Notice Period",       "90 days written notice"],
        ["Jurisdiction",        "California, USA"],
    ], col_widths=[2.2*inch, 4.0*inch]), sp()]

    story += [p("2. Pricing Schedule", H2)]
    story += [tbl([
        ["Service Line",            "Unit",       "Unit Price", "Contracted Units",  "Annual Value"],
        ["Compute (vCPU-hr)",       "vCPU-hour",  "$0.048",     "12,500,000 hrs",    "$600,000"],
        ["Storage (object)",        "TB-month",   "$18.50",     "2,400 TB-mo.",      "$444,000"],
        ["Egress Bandwidth",        "TB",         "$0.07",      "85,000 TB/yr",      "$595,000 est."],
        ["Managed Kubernetes",      "Cluster/mo", "$1,800",     "8 clusters",        "$172,800"],
        ["Support (Enterprise)",    "Flat / yr",  "$95,000",    "1",                 "$95,000"],
        ["Professional Services",   "Day rate",   "$2,200",     "200 days/yr",       "$440,000"],
        ["Security and Compliance", "Flat / mo",  "$12,500",    "12 months",         "$150,000"],
    ], col_widths=[1.8*inch, 1.1*inch, 1.0*inch, 1.4*inch, 1.2*inch]), sp()]

    story += [p("3. Service Commitments", H2)]
    story += [p(
        'Vendor commits to maintaining the following service levels for all production workloads. '
        'Failures to meet commitments shall trigger the credit mechanism defined in Exhibit B. '
        'Vendor shall provide monthly SLA reports no later than the 5th business day of the '
        'following month. NBCU retains the right to audit Vendor monitoring data upon 10 '
        'business days written notice.'
    )]
    story += [tbl([
        ["Service",            "Availability SLA", "RTO",   "RPO"],
        ["Compute Platform",   "99.99 %",          "5 min", "0 min"],
        ["Object Storage",     "99.999 %",         "N/A",   "0 min"],
        ["Managed Kubernetes", "99.95 %",          "15 min","5 min"],
        ["CDN Delivery",       "99.98 %",          "10 min","N/A"],
        ["Security Services",  "99.9 %",           "30 min","15 min"],
    ], col_widths=[2.0*inch, 1.7*inch, 1.3*inch, 1.3*inch]), sp()]

    story += [p("4. Key Personnel", H2)]
    story += [tbl([
        ["Role",                      "Name",         "Responsibilities"],
        ["Engagement Director",       "Lena Vasquez", "Contract governance, executive reporting"],
        ["Solutions Architect",       "Tom Nguyen",   "Technical design, migration planning"],
        ["Site Reliability Engineer", "Priya Sharma", "Operations, incident response"],
        ["Security Lead",             "Carlos Reyes", "Compliance, pen-testing coordination"],
        ["NBCU Contract Owner",       "Rachel Bloom", "NBCU-side approvals and escalations"],
    ], col_widths=[1.8*inch, 1.5*inch, 3.0*inch]), sp()]

    story += [p("5. Termination and Penalties", H2)]
    story += [p(
        'Either party may terminate for cause upon 30 days written notice following an uncured '
        'material breach. NBCU may terminate for convenience with 90 days written notice, subject '
        'to payment of a termination fee equal to 10 % of the remaining contract value. Early '
        'termination by Vendor without cause entitles NBCU to liquidated damages of $500,000.'
    ), sp()]

    doc("sample3_vendor_contract_original.pdf").build(story)
    print("  sample3_vendor_contract_original.pdf")


# ---------------------------------------------------------------------------
# SAMPLE 1B  --  SLA with intentional discrepancies (based on Sample 1)
#
# CHANGED : Contract Value $2,400,000 -> $1,950,000
#           Billing Cycle Monthly -> Quarterly
#           Platform Uptime 99.95% -> 99.90%
#           Stream Start Time <= 2.0 sec -> <= 2.5 sec
#           Error Rate penalty threshold > 0.3% -> > 0.5%
#           Credit Minor 5% -> 3%  |  Critical 50% -> 40%
#           Maintenance Standard window 4 hrs -> 6 hrs
#           Technical Lead name/email changed (Marcus Webb -> David Chen)
#           Account Manager phone changed
# REMOVED :  Dispute Resolution row
#            CDN Cache-Hit Ratio row
#            Support Resolution (P1) row
#            Executive Sponsor row
# ---------------------------------------------------------------------------
def build_sample1b():
    story = []
    story += [p("SERVICE LEVEL AGREEMENT", H1), hr()]
    story += [p(
        'This Service Level Agreement (the Agreement) is entered into as of January 15, 2025, '
        'between NBCUniversal Media, LLC (Client) and StreamTech Solutions, Inc. (Provider). '
        'This Agreement defines the service standards, performance metrics, and remediation '
        'procedures governing the video streaming infrastructure services provided to Client.'
    ), sp()]

    story += [p("1. Agreement Overview", H2)]
    story += [tbl([
        ["Field",           "Value"],
        ["Contract ID",     "SLA-2025-0042"],
        ["Effective Date",  "January 15, 2025"],
        ["Expiration Date", "January 14, 2026"],
        ["Contract Value",  "$1,950,000 USD"],          # CHANGED
        ["Billing Cycle",   "Quarterly"],               # CHANGED
        ["Governing Law",   "State of New York"],
        # Dispute Resolution -- REMOVED
    ], col_widths=[2.2*inch, 4.0*inch]), sp()]

    story += [p("2. Service Performance Targets", H2)]
    story += [tbl([
        ["Metric",                "Target",    "Measurement Window", "Penalty Threshold"],
        ["Platform Uptime",       "99.90 %",   "Monthly",            "< 99.9 %"],   # CHANGED
        ["Stream Start Time",     "<= 2.5 sec","Weekly avg.",         "> 3.0 sec"],  # CHANGED
        ["Buffering Ratio",       "< 0.5 %",   "Weekly avg.",         "> 1.0 %"],
        ["Error Rate (5xx)",      "< 0.1 %",   "Daily avg.",          "> 0.5 %"],   # CHANGED
        # CDN Cache-Hit Ratio -- REMOVED
        ["Support Response (P1)", "<= 15 min", "Per incident",        "> 30 min"],
        # Support Resolution (P1) -- REMOVED
    ], col_widths=[2.2*inch, 1.2*inch, 1.6*inch, 1.6*inch]), sp()]

    story += [p("3. Penalty and Credit Structure", H2)]
    story += [p(
        'In the event that Provider fails to meet any performance target defined in Section 2, '
        'Client shall be entitled to a Service Credit calculated as a percentage of the monthly '
        'fee for the affected service tier. Credits are applied to the following invoice and are '
        'non-transferable. Credits do not constitute a waiver of any other rights or remedies '
        'available to Client under this Agreement or applicable law.'
    )]
    story += [tbl([
        ["Severity", "Breach Duration", "Credit (% of Monthly Fee)"],
        ["Minor",    "< 1 hour",         "3 %"],           # CHANGED
        ["Moderate", "1 - 4 hours",      "15 %"],
        ["Major",    "4 - 8 hours",      "30 %"],
        ["Critical", "> 8 hours",        "40 %"],          # CHANGED
    ], col_widths=[1.5*inch, 2.0*inch, 3.0*inch]), sp()]

    story += [p("4. Maintenance Windows", H2)]
    story += [p(
        'Provider may conduct scheduled maintenance during the approved windows listed below '
        'without incurring SLA penalties, provided that Client receives no fewer than 72 hours '
        'of advance written notice. Emergency maintenance required to prevent imminent service '
        'degradation may be performed with 4 hours notice; any associated downtime will be '
        'excluded from uptime calculations for penalty purposes only.'
    )]
    story += [tbl([
        ["Window",    "Day(s)",        "Time (ET)",      "Max Duration"],
        ["Standard",  "Sunday",        "02:00 - 06:00",  "6 hours"],      # CHANGED
        ["Extended",  "1st Sun/Month", "00:00 - 08:00",  "8 hours"],
        ["Emergency", "Any",           "As required",    "2 hours"],
    ], col_widths=[1.5*inch, 1.8*inch, 2.0*inch, 2.0*inch]), sp()]

    story += [p("5. Escalation Contacts", H2)]
    story += [tbl([
        ["Role",            "Name",        "Email",                     "Phone"],
        ["Account Manager", "Sarah Kim",   "s.kim@streamtech.io",       "+1 212 555 0199"],  # CHANGED phone
        ["Technical Lead",  "David Chen",  "d.chen@streamtech.io",      "+1 212 555 0102"],  # CHANGED name/email
        # Executive Sponsor -- REMOVED
        ["Client POC",      "James Ortega","j.ortega@nbcuniversal.com", "+1 212 664 0200"],
    ], col_widths=[1.5*inch, 1.5*inch, 2.4*inch, 1.4*inch]), sp()]

    doc("sample1b_sla_modified.pdf").build(story)
    print("  sample1b_sla_modified.pdf")


# ---------------------------------------------------------------------------
# SAMPLE 2B  --  Tech Spec with intentional discrepancies (based on Sample 2)
#
# CHANGED : Version 4.2.1 -> 4.3.0
#           Release Date Nov 8 2024 -> Feb 14 2025
#           Last Audit Date Dec 18 2024 -> Mar 5 2025
#           4K-HDR bitrate 20 Mbps -> 18 Mbps
#           1080p-HQ bitrate 8 Mbps -> 6 Mbps
#           720p frame rate 30 fps -> 60 fps
#           Audio 5.1 bitrate 640 kbps -> 512 kbps
#           MPEG-DASH segment 6 sec -> 4 sec
#           CDN origin shield Ashburn VA -> Chicago IL
#           Origin Servers 24 -> 16
#           Encoding Workers 48 -> 32
#           CDN PoPs 142 -> 138
#           Encoding Completion Rate 99.87% -> 99.74% (FAIL)
#           Avg. Encoding Latency (4K) 4.2 min -> 6.1 min (FAIL)
#           DRM License Issuance 210 ms -> 340 ms (FAIL)
#           VMAF Score 93.2 -> 91.8 (FAIL)
# REMOVED :  Review Cycle row
#            360p codec row
#            Storage (cold tier) row
#            Package Error Rate metric row
# ---------------------------------------------------------------------------
def build_sample2b():
    story = []
    story += [p("STREAMING PLATFORM TECHNICAL SPECIFICATION", H1), hr()]
    story += [p(
        'This document provides the technical baseline specification for the NBCUniversal Peacock '
        'streaming platform encoding pipeline, Version 4.2. It covers codec profiles, packaging '
        'formats, CDN integration requirements, and quality-of-service targets. All figures are '
        'as-built values validated during the Q4 2024 performance audit unless otherwise noted.'
    ), sp()]

    story += [p("1. System Identification", H2)]
    story += [tbl([
        ["Parameter",       "Value"],
        ["System Name",     "Peacock Encoding Pipeline"],
        ["Version",         "4.3.0"],                   # CHANGED
        ["Release Date",    "February 14, 2025"],       # CHANGED
        ["Owner",           "Platform Engineering - NBCU"],
        ["Classification",  "Internal / Confidential"],
        # Review Cycle -- REMOVED
        ["Last Audit Date", "March 5, 2025"],           # CHANGED
    ], col_widths=[2.2*inch, 4.0*inch]), sp()]

    story += [p("2. Codec and Encoding Profiles", H2)]
    story += [tbl([
        ["Profile",   "Codec",  "Resolution", "Bitrate",  "Frame Rate", "HDR"],
        ["4K-HDR",    "HEVC",   "3840x2160",  "18 Mbps",  "60 fps",     "HDR10+"],   # CHANGED
        ["1080p-HQ",  "AVC",    "1920x1080",  "6 Mbps",   "60 fps",     "SDR"],      # CHANGED
        ["1080p-SD",  "AVC",    "1920x1080",  "4.5 Mbps", "30 fps",     "SDR"],
        ["720p",      "AVC",    "1280x720",   "2.5 Mbps", "60 fps",     "SDR"],      # CHANGED frame rate
        ["480p",      "AVC",    "854x480",    "1.0 Mbps", "30 fps",     "SDR"],
        # 360p -- REMOVED
        ["Audio 5.1", "EAC3",   "N/A",        "512 kbps", "N/A",        "N/A"],      # CHANGED
        ["Audio 2.0", "AAC-LC", "N/A",        "192 kbps", "N/A",        "N/A"],
    ], col_widths=[1.1*inch, 0.9*inch, 1.3*inch, 1.0*inch, 1.0*inch, 1.0*inch]), sp()]

    story += [p("3. Packaging and Delivery", H2)]
    story += [p(
        'Content is packaged in MPEG-DASH (ISO BMFF) with a 4-second segment duration and '
        'HLS (CMAF) with a 6-second segment duration for Apple device compatibility. '
        'DRM is enforced via Widevine (L1/L3), PlayReady (SL3000), and FairPlay. '
        'All manifests are generated by the Unified Packager v3.7 and distributed through '
        'the Akamai EdgeSuite CDN with an origin shield in Chicago, IL.'
    )]
    story += [tbl([
        ["Format",        "Segment Duration", "DRM",                  "Target Device"],
        ["MPEG-DASH",     "4 seconds",        "Widevine / PlayReady", "Android, Web, CTV"],  # CHANGED
        ["HLS (CMAF)",    "6 seconds",        "FairPlay",             "iOS, macOS, tvOS"],
        ["Smooth Stream", "4 seconds",        "PlayReady SL3000",     "Xbox, Windows"],
    ], col_widths=[1.4*inch, 1.5*inch, 2.0*inch, 2.0*inch]), sp()]

    story += [p("4. Infrastructure and Capacity", H2)]
    story += [tbl([
        ["Component",           "Specification",          "Count / Capacity"],
        ["Origin Servers",      "AWS EC2 c5.4xlarge",     "16 instances (auto-scale)"],   # CHANGED
        ["Encoding Workers",    "AWS EC2 c5n.18xlarge",   "32 instances (spot fleet)"],   # CHANGED
        ["Storage (hot tier)",  "AWS S3 Standard",        "2.4 PB allocated"],
        # Storage cold tier -- REMOVED
        ["Database (metadata)", "Aurora PostgreSQL 15.4", "Multi-AZ, r6g.4xlarge"],
        ["Message Queue",       "Apache Kafka 3.6",       "9-node cluster"],
        ["CDN PoP Coverage",    "Akamai EdgeSuite",       "138 PoPs globally"],           # CHANGED
    ], col_widths=[2.0*inch, 2.4*inch, 2.3*inch]), sp()]

    story += [p("5. Quality Metrics (Q4 2024 Audit)", H2)]
    story += [tbl([
        ["Metric",                        "Measured Value", "Target",   "Status"],
        ["Encoding Completion Rate",      "99.74 %",        ">= 99.8 %","FAIL"],  # CHANGED
        ["Avg. Encoding Latency (4K)",    "6.1 min",        "<= 5 min", "FAIL"],  # CHANGED
        ["Avg. Encoding Latency (1080p)", "1.8 min",        "<= 3 min", "PASS"],
        # Package Error Rate -- REMOVED
        ["DRM License Issuance (p99)",    "340 ms",         "< 300 ms", "FAIL"],  # CHANGED
        ["CDN Origin Pull Error Rate",    "0.07 %",         "< 0.2 %",  "PASS"],
        ["VMAF Score (4K-HDR avg.)",      "91.8",           ">= 92",    "FAIL"],  # CHANGED
    ], col_widths=[2.5*inch, 1.5*inch, 1.2*inch, 1.0*inch]), sp()]

    doc("sample2b_techspec_modified.pdf").build(story)
    print("  sample2b_techspec_modified.pdf")


# ---------------------------------------------------------------------------
print("Generating PDFs in samples/")
build_sample1()
build_sample2()
build_sample3()
build_sample1b()
build_sample2b()
print("Done.")
