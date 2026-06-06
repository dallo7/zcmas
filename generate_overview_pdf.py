"""Generate ZCAMS-Overview.pdf describing the project, the problem it solves,
and its feature set. Run with the cfa-dash venv:

    .\\cfa-dash\\.venv\\Scripts\\python.exe generate_overview_pdf.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


# --------------------------------------------------------------------------- colors
ZAFFA_GREEN = colors.HexColor("#1f6b3b")
ZAFFA_GREEN_DARK = colors.HexColor("#0d3a1f")
ZAFFA_LIME = colors.HexColor("#7ec253")
SUBTLE_GREY = colors.HexColor("#4a4f4a")
PANEL_BG = colors.HexColor("#f4f9ef")
PANEL_BORDER = colors.HexColor("#cfe5c7")


# --------------------------------------------------------------------------- styles
styles = getSampleStyleSheet()

H_TITLE = ParagraphStyle(
    "TitleBig", parent=styles["Title"],
    fontName="Helvetica-Bold", fontSize=34, leading=40,
    textColor=ZAFFA_GREEN_DARK, alignment=TA_LEFT, spaceAfter=6,
)
H_SUBTITLE = ParagraphStyle(
    "Subtitle", parent=styles["Title"],
    fontName="Helvetica", fontSize=15, leading=20,
    textColor=ZAFFA_GREEN, alignment=TA_LEFT, spaceAfter=4,
)
H_TAGLINE = ParagraphStyle(
    "Tagline", parent=styles["BodyText"],
    fontName="Helvetica-Oblique", fontSize=12, leading=18,
    textColor=SUBTLE_GREY, alignment=TA_LEFT, spaceAfter=18,
)
H_META = ParagraphStyle(
    "Meta", parent=styles["BodyText"],
    fontName="Helvetica", fontSize=10, leading=14,
    textColor=SUBTLE_GREY, alignment=TA_LEFT,
)

H1 = ParagraphStyle(
    "H1", parent=styles["Heading1"],
    fontName="Helvetica-Bold", fontSize=20, leading=26,
    textColor=ZAFFA_GREEN_DARK, spaceBefore=16, spaceAfter=10,
)
H2 = ParagraphStyle(
    "H2", parent=styles["Heading2"],
    fontName="Helvetica-Bold", fontSize=13, leading=18,
    textColor=ZAFFA_GREEN, spaceBefore=12, spaceAfter=6,
)
BODY = ParagraphStyle(
    "Body", parent=styles["BodyText"],
    fontName="Helvetica", fontSize=10.5, leading=15,
    textColor=colors.HexColor("#1c2419"), alignment=TA_JUSTIFY, spaceAfter=8,
)
BULLET = ParagraphStyle(
    "Bullet", parent=BODY, leftIndent=8, bulletIndent=0,
    alignment=TA_LEFT, spaceAfter=2,
)
CALLOUT = ParagraphStyle(
    "Callout", parent=BODY, fontSize=10.5, leading=15,
    textColor=ZAFFA_GREEN_DARK, alignment=TA_LEFT,
)
SMALL = ParagraphStyle(
    "Small", parent=BODY, fontSize=9, leading=12,
    textColor=SUBTLE_GREY, alignment=TA_LEFT,
)


# --------------------------------------------------------------------------- helpers
def panel(flowables, *, bg=PANEL_BG, border=PANEL_BORDER):
    """Wrap flowables in a single-cell table styled as a callout box."""
    tbl = Table([[flowables]], colWidths=[None])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.8, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return tbl


def bullet_list(items: list[str], style=BULLET, bullet_color=ZAFFA_GREEN):
    flowables = []
    for it in items:
        flowables.append(
            ListItem(
                Paragraph(it, style),
                leftIndent=12,
                value="circle",
                bulletColor=bullet_color,
            )
        )
    return ListFlowable(flowables, bulletType="bullet", start="circle", bulletFontSize=6)


def two_col(left, right, gap=8 * mm, left_w=None, right_w=None):
    if left_w is None and right_w is None:
        left_w = right_w = (A4[0] - 2 * 2 * cm - gap) / 2
    tbl = Table([[left, right]], colWidths=[left_w, right_w])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return tbl


# --------------------------------------------------------------------------- page chrome
def _draw_cover_background(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(ZAFFA_GREEN_DARK)
    canvas.rect(0, h - 4.6 * cm, w, 4.6 * cm, stroke=0, fill=1)
    canvas.setFillColor(ZAFFA_LIME)
    canvas.rect(0, h - 4.85 * cm, w, 0.25 * cm, stroke=0, fill=1)
    canvas.setFillColor(ZAFFA_GREEN)
    canvas.rect(0, 0, w, 1.6 * cm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(2 * cm, 0.6 * cm, "ZCAMS  |  Zambia Customs Agent Management System")
    canvas.drawRightString(w - 2 * cm, 0.6 * cm, "ZAFFA Clearing & Forwarding")
    canvas.restoreState()


def _draw_content_chrome(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(ZAFFA_GREEN_DARK)
    canvas.rect(0, h - 1.4 * cm, w, 1.4 * cm, stroke=0, fill=1)
    canvas.setFillColor(ZAFFA_LIME)
    canvas.rect(0, h - 1.55 * cm, w, 0.15 * cm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(2 * cm, h - 0.95 * cm, "ZCAMS  \u2014  Project Overview")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(w - 2 * cm, h - 0.95 * cm, "ZAFFA Clearing & Forwarding")
    # Footer
    canvas.setFillColor(ZAFFA_GREEN)
    canvas.rect(0, 0, w, 1.0 * cm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 8.5)
    canvas.drawString(2 * cm, 0.35 * cm, "ZCAMS POC \u2014 Built on Plotly Dash, SQLite, CapitalPay, Bird Email")
    canvas.drawRightString(w - 2 * cm, 0.35 * cm, f"Page {doc.page}")
    canvas.restoreState()


# --------------------------------------------------------------------------- document
class ZcamsDoc(BaseDocTemplate):
    def __init__(self, filename: str):
        super().__init__(
            filename, pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=2.2 * cm, bottomMargin=1.8 * cm,
            title="ZCAMS Project Overview",
            author="ZAFFA Clearing & Forwarding",
            subject="Zambia Customs Agent Management System \u2014 POC overview",
        )
        cover_frame = Frame(
            self.leftMargin, self.bottomMargin,
            self.width, self.height + 0.4 * cm,
            id="cover",
        )
        content_frame = Frame(
            self.leftMargin, self.bottomMargin,
            self.width, self.height - 0.8 * cm,
            id="content",
        )
        self.addPageTemplates([
            PageTemplate(id="Cover", frames=[cover_frame], onPage=_draw_cover_background),
            PageTemplate(id="Content", frames=[content_frame], onPage=_draw_content_chrome),
        ])


# --------------------------------------------------------------------------- content builder
def build_story() -> list:
    today = datetime.now().strftime("%B %Y")
    story: list = []

    # ---------------------------------------------------------------- COVER
    story.append(Spacer(1, 6 * cm))
    story.append(Paragraph("ZCAMS", H_TITLE))
    story.append(Paragraph("Zambia Customs Agent Management System", H_SUBTITLE))
    story.append(Paragraph(
        "An end-to-end digital workflow for CFA onboarding, Bill of Lading review, "
        "Z-SAD issuance, GN 83-compliant invoicing, CapitalPay settlement, and cargo release.",
        H_TAGLINE,
    ))
    story.append(Spacer(1, 8 * cm))
    story.append(panel([
        Paragraph("Prepared for", SMALL),
        Paragraph("<b>ZAFFA Clearing &amp; Forwarding</b>", CALLOUT),
        Spacer(1, 6),
        Paragraph("Document type", SMALL),
        Paragraph("<b>Proof-of-Concept overview</b>", CALLOUT),
        Spacer(1, 6),
        Paragraph("Issued", SMALL),
        Paragraph(f"<b>{today}</b>", CALLOUT),
    ]))
    story.append(PageBreak())
    story.append(Spacer(1, 0.2 * cm))

    # ---------------------------------------------------------------- EXEC SUMMARY
    story.append(Paragraph("Executive Summary", H1))
    story.append(Paragraph(
        "ZCAMS is a working proof-of-concept that automates the day-to-day operations of a "
        "Clearing &amp; Forwarding Agent (CFA) in Zambia. Built as a Plotly Dash web application "
        "with a SQLite back-end, it covers the full cargo-clearance lifecycle\u2014from a CFA's "
        "first onboarding request through ZAFFA approval, Bill of Lading capture, Z-SAD "
        "issuance, GN 83-compliant invoice generation, CapitalPay payment settlement, and "
        "final cargo release.",
        BODY,
    ))
    story.append(Paragraph(
        "The POC replaces a fragmented mix of paper forms, spreadsheets, email threads, "
        "and ad-hoc bank instructions with a single auditable system that enforces statutory "
        "fee rules, signs every invoice through CapitalPay, and shares each invoice with the "
        "importer over WhatsApp, SMS, and email automatically.",
        BODY,
    ))

    # ---------------------------------------------------------------- PROBLEM
    story.append(Paragraph("The Problem", H1))
    story.append(Paragraph(
        "Customs clearing in Zambia is a high-volume, high-risk process governed by "
        "Government Notice 83 (GN 83), which prescribes minimum agency fees by route, "
        "transport mode, and cargo category. Today the process is handled with manual "
        "tools that introduce five recurring problems:",
        BODY,
    ))
    story.append(bullet_list([
        "<b>Inconsistent fee enforcement.</b> Service-fee and full-settlement invoices are "
        "calculated by hand, so the GN 83 minimum, the 20% administrative fee, and the 16% "
        "VAT are frequently misapplied or omitted entirely.",
        "<b>Price undercutting.</b> Without a system-enforced floor, competing CFAs quote "
        "below the GN 83 statutory minimum to win work. This erodes margins for compliant "
        "agents, distorts the market, and leaves ZAFFA with no objective way to police the "
        "tariff its members are required to observe.",
        "<b>Late and unpredictable payments.</b> Importers receive invoices through "
        "informal channels, often without a working payment link, so settlement is delayed "
        "by days or weeks while the CFA chases reminders manually. Cargo sits at the "
        "border accruing demurrage and the agent finances the gap from working capital.",
        "<b>Untraceable Z-SAD usage.</b> Single-use Z-SAD numbers are recycled, lost, or "
        "issued against the wrong Bill of Lading, leaving no paper trail when ZRA queries "
        "a clearance.",
        "<b>Manual importer communications.</b> Invoices are emailed individually, payment "
        "links are pasted into chat apps, and cargo release confirmations are sent verbally, "
        "so disputes about what was sent, when, and to whom are unavoidable.",
    ]))
    story.append(Paragraph(
        "The cumulative effect is slow turnaround, revenue leakage from under-invoiced and "
        "underpriced jobs, working capital tied up in unpaid invoices, and exposure during "
        "ZRA audits.",
        BODY,
    ))

    story.append(PageBreak())

    # ---------------------------------------------------------------- SOLUTION
    story.append(Paragraph("The ZCAMS Solution", H1))
    story.append(Paragraph(
        "ZCAMS turns the clearance workflow into a guided, rule-enforced pipeline. Each "
        "step writes to a SQLite store with audit trails, every invoice is cryptographically "
        "signed via CapitalPay before it is released, and every importer-facing message is "
        "dispatched through the platform so it can be replayed if a dispute arises.",
        BODY,
    ))

    story.append(Paragraph("How a clearance flows through ZCAMS", H2))
    story.append(Paragraph("The CFA staff member proceeds through nine numbered stages:", BODY))
    story.append(bullet_list([
        "<b>1. CFA onboarding.</b> A clearing agent applies through a public form; ZAFFA "
        "approves or rejects the registration and login credentials are emailed automatically.",
        "<b>2. Bill of Lading capture.</b> Uploaded BL PDFs are OCR-extracted (OpenAI/Groq "
        "adapter) and persisted, or captured manually if OCR is unavailable.",
        "<b>3. Reviewed BL &amp; Z-SAD.</b> Each BL is reviewed and assigned a single-use "
        "Z-SAD number with strict uniqueness; corrections require an explicit detach that "
        "retires the old number and cancels its invoice.",
        "<b>4. Invoice request.</b> The CFA chooses <i>Full Settlement</i> or "
        "<i>Full Settlement</i>; ZCAMS calculates the GN 83 minimum, the 20% admin fee, "
        "and 16% VAT, ceiling each line.",
        "<b>5. CapitalPay signing.</b> The invoice is sent to CapitalPay for signing and "
        "the returned URN is stamped onto the PDF. Mock invoices are refused in production.",
        "<b>6. Importer share.</b> The signed PDF is dispatched to the importer over the "
        "selected channels: WhatsApp click-to-chat, SMS, and an email with the PDF attached "
        "via the Bird Reach API.",
        "<b>7. CapitalPay check-out.</b> A payment link is generated; settlement status is "
        "tracked against the invoice.",
        "<b>8. Cargo release.</b> Full Settlement auto-releases on payment; Full Settlement "
        "enables a manual release once the bank confirms the importer payment.",
        "<b>9. Audit &amp; communication.</b> Every action writes a notification record; "
        "the ZCAMS Chat module answers Gazette Notice questions for the CFA.",
    ]))

    story.append(Paragraph("Outcome", H2))
    story.append(panel([
        Paragraph(
            "Turnaround time drops from days to minutes because the system enforces "
            "the rules, signs the invoice, and notifies the importer in a single click. "
            "Because every invoice is generated from the GN 83 schedule and signed by "
            "CapitalPay, <b>price undercutting becomes impossible</b>\u2014the statutory "
            "floor is the cheapest invoice the system will ever produce. And because the "
            "signed PDF ships with a live CapitalPay check-out link to WhatsApp, SMS, "
            "and email at the same moment it is created, importers <b>pay promptly</b> "
            "instead of waiting on manual reminders. Every Z-SAD, invoice, payment, and "
            "release is preserved with a timestamp, making ZRA audits a query rather "
            "than an investigation.",
            CALLOUT,
        ),
    ]))

    story.append(PageBreak())

    # ---------------------------------------------------------------- MODULES
    story.append(Paragraph("Module Catalogue", H1))
    story.append(Paragraph(
        "ZCAMS ships with fourteen modules accessible from the persistent sidebar. "
        "Each module is a self-contained Dash page that talks to the shared SQLite "
        "repository.",
        BODY,
    ))

    modules = [
        ("Login / Onboarding", "Public CFA registration, ZAFFA approval, automated credential emails."),
        ("Dashboard", "At-a-glance KPIs: active BLs, pending Z-SADs, outstanding invoices, recent payments."),
        ("BLs", "Upload or manually capture Bills of Lading; OCR-assisted data extraction."),
        ("Reviewed BL", "Issue and manage Z-SAD numbers; safe detach &amp; reissue when corrections are needed."),
        ("Invoices", "Browse the invoice register, filter by status, and re-download signed PDFs."),
        ("Check-out", "CapitalPay payment links and live settlement status per invoice."),
        ("Contracts", "Importer/CFA contract templates and execution records."),
        ("Certificates", "Single-use certificate evidence linked to the underlying BL and Z-SAD."),
        ("Company Profile", "CFA company details, banking information, and authorised signatories."),
        ("Notifications", "Append-only audit feed of every state change with timestamp and actor."),
        ("Support", "In-app ticket queue and contact channels for the CFA team."),
        ("ZCAMS Chat", "Gazette Notice-aware FAQ assistant; optional local LLM (Qwen 2.5 0.5B)."),
        ("GN 83 Schedule", "Browsable reference of every GN 83 minimum-fee row used for invoice calculation."),
    ]
    rows = [[Paragraph(f"<b>{name}</b>", BODY), Paragraph(desc, BODY)] for name, desc in modules]
    table = Table(rows, colWidths=[4.6 * cm, None])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), PANEL_BG),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, PANEL_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)

    story.append(PageBreak())

    # ---------------------------------------------------------------- FEATURES
    story.append(Paragraph("Feature Highlights", H1))

    left = [
        Paragraph("Workflow &amp; compliance", H2),
        bullet_list([
            "End-to-end pipeline from onboarding to cargo release.",
            "Strict Z-SAD uniqueness with safe detach &amp; reissue.",
            "Single-use BL number enforcement.",
            "Cancellation cascade: detaching a Z-SAD cancels its invoice.",
            "Release gate for Full Settlement flows.",
            "Auto-release on Full Settlement after payment confirmation.",
        ]),
        Paragraph("Invoicing &amp; payments", H2),
        bullet_list([
            "GN 83 minimum fee lookup by route, mode, and cargo category.",
            "Full Settlement: 20% admin + 16% VAT (ceiled to whole cents).",
            "Full Settlement: GN 83 minimum + 20% admin + 16% VAT (ceiled).",
            "CapitalPay signing with refusal of mock URNs in production.",
            "PDF invoice generation via ReportLab; signed copies persisted.",
            "CapitalPay check-out link generation per invoice.",
        ]),
    ]
    right = [
        Paragraph("Importer communications", H2),
        bullet_list([
            "WhatsApp click-to-chat link auto-opens in a new browser tab.",
            "SMS share for low-bandwidth recipients.",
            "Bird Reach API email with the signed PDF attached.",
            "Per-channel delivery status reported back to the CFA.",
            "Notifications table records every share attempt with timestamp.",
        ]),
        Paragraph("Operational &amp; audit", H2),
        bullet_list([
            "SQLite store created automatically on first launch.",
            "Append-only notifications/audit feed.",
            "Server-side error capture surfaces failures inside the modal.",
            "File-based <i>invoice_flow.log</i> for deep diagnostics.",
            "GN 83 Schedule reference page for traceable fee lookups.",
            "ZCAMS Chat for in-app Gazette Notice questions.",
        ]),
    ]
    story.append(two_col(left, right))

    story.append(PageBreak())

    # ---------------------------------------------------------------- RULES
    story.append(Paragraph("Business Rules Enforced", H1))
    story.append(panel([
        Paragraph("Bills of Lading", H2),
        bullet_list([
            "BL number must be unique within ZCAMS.",
            "Doc type, route, transport mode, and ZRA regime are mandatory.",
            "OCR-extracted fields are presented for human review before save.",
        ]),
        Paragraph("Z-SAD numbers", H2),
        bullet_list([
            "Each Z-SAD is single-use and globally unique.",
            "Detaching a Z-SAD retires the number and cancels its invoice.",
            "Z-SAD history is preserved on the reviewed BL record.",
        ]),
        Paragraph("Invoices &amp; payments", H2),
        bullet_list([
            "GN 83 minimum fee is the floor for Full Settlement invoices.",
            "All money values are ceiled to two decimals to avoid rounding loss.",
            "Mock CapitalPay invoices (<i>CPAYMOCK\u2026</i>) are refused unless "
            "<code>CAPITALPAY_MODE=mock</code> is set explicitly.",
            "Full Settlement auto-releases the cargo on successful settlement.",
            "Full Settlement proceeds to cargo release after settlement confirmation.",
        ]),
    ]))

    # ---------------------------------------------------------------- INTEGRATIONS
    story.append(Paragraph("Integrations", H1))
    integ_rows = [
        ["Integration", "Purpose", "Status"],
        ["CapitalPay", "Invoice signing, check-out links, settlement webhook.", "Live (real credentials)"],
        ["Bird Reach API", "Importer email with signed PDF attachment.", "Live (real credentials)"],
        ["OpenAI / Groq OCR", "Bill of Lading data extraction.", "Adapter \u2014 enable via .env"],
        ["WhatsApp click-to-chat", "Importer messaging via wa.me deep link.", "Live (no API key required)"],
        ["Gmail SMTP", "Onboarding approval emails.", "Optional fallback"],
        ["HuggingFace Transformers", "Local Qwen 2.5 0.5B for ZCAMS Chat.", "Opt-in (CHAT_MODEL_ENABLED=true)"],
    ]
    table = Table(integ_rows, colWidths=[4.4 * cm, 7.2 * cm, 5.2 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ZAFFA_GREEN_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, PANEL_BG]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, PANEL_BORDER),
    ]))
    story.append(table)

    story.append(PageBreak())

    # ---------------------------------------------------------------- TECH STACK
    story.append(Paragraph("Technology Stack", H1))
    story.append(Paragraph(
        "ZCAMS is deliberately built on a small, well-understood stack so it can be "
        "deployed by a single operator without a dedicated DevOps function.",
        BODY,
    ))
    tech_rows = [
        ["Layer", "Technology"],
        ["Web framework", "Plotly Dash 4.1 (Flask under the hood)"],
        ["UI components", "Dash Mantine Components, Dash Iconify, custom CSS theme"],
        ["Server runtime", "Python 3.13, Werkzeug 3.1 development server"],
        ["Persistence", "SQLite (bundled, file-based)"],
        ["PDF generation", "ReportLab 4.5"],
        ["Document OCR", "PyMuPDF, pdf2image, Pillow + OpenAI/Groq adapter"],
        ["Payments", "CapitalPay REST API"],
        ["Email", "Bird Reach API (Gmail SMTP fallback)"],
        ["Optional LLM", "HuggingFace Transformers + Qwen 2.5 0.5B"],
        ["Testing", "pytest 9, Dash test client"],
    ]
    table = Table(tech_rows, colWidths=[5.0 * cm, None])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ZAFFA_GREEN_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, PANEL_BG]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, PANEL_BORDER),
    ]))
    story.append(table)

    # ---------------------------------------------------------------- GETTING STARTED
    story.append(Paragraph("Getting Started", H1))
    story.append(Paragraph("Run the POC", H2))
    story.append(panel([
        Paragraph("From the workspace root in PowerShell:", SMALL),
        Spacer(1, 4),
        Paragraph("<font face='Courier'>.\\run-zcams.ps1</font>", CALLOUT),
        Spacer(1, 6),
        Paragraph("Then open:", SMALL),
        Paragraph("<font face='Courier'>http://127.0.0.1:8050/</font>", CALLOUT),
    ]))
    story.append(Paragraph("Run the test suite", H2))
    story.append(panel([
        Paragraph("<font face='Courier'>.\\test-zcams.ps1</font>", CALLOUT),
        Spacer(1, 4),
        Paragraph(
            "Covers routing, invoice flow, Z-SAD detach, GN 83 lookup, and the live "
            "CapitalPay integration where credentials are present.",
            SMALL,
        ),
    ]))

    story.append(Paragraph("Operational notes", H2))
    story.append(bullet_list([
        "The SQLite database is created automatically at <i>cfa-dash/data/zcams.db</i> on first launch.",
        "Real CapitalPay signing is enforced; mock invoices are refused unless "
        "<code>CAPITALPAY_MODE=mock</code> is set explicitly.",
        "Every invoice action is logged to <i>cfa-dash/data/invoice_flow.log</i> for diagnostics.",
        "Server-side errors are surfaced inside the invoice modal so the CFA never has to "
        "guess why a request failed.",
    ]))

    story.append(Spacer(1, 0.6 * cm))
    story.append(panel([
        Paragraph(
            "<b>Status:</b> the POC is feature-complete for the nine-stage clearance workflow "
            "and has been verified end-to-end against live CapitalPay signing and Bird Reach "
            "email delivery. The next milestone is hardening for multi-tenant deployment and "
            "wiring the OCR adapter to a production OpenAI/Groq workspace.",
            CALLOUT,
        ),
    ]))

    return story


def main() -> int:
    out_path = Path(__file__).resolve().parent / "ZCAMS-Overview.pdf"
    doc = ZcamsDoc(str(out_path))
    doc.build(build_story())
    print(f"Generated: {out_path}  ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
