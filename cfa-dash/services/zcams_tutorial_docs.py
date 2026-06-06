"""Generate polished ZCAMS tutorial and ASYCUDA integration PDFs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

GREEN = colors.HexColor("#06451F")
GREEN_DARK = colors.HexColor("#031F0C")
GREEN_SOFT = colors.HexColor("#EAF6EC")
MINT = colors.HexColor("#F2FAF4")
PANEL = colors.HexColor("#FBFEFB")
GOLD = colors.HexColor("#C9A227")
ORANGE = colors.HexColor("#EF7D00")
YELLOW = colors.HexColor("#F5B700")
RED = colors.HexColor("#8B1E1E")
BLUE = colors.HexColor("#0033A0")
TEXT = colors.HexColor("#1A2E24")
MUTED = colors.HexColor("#4A5D52")
GRID = colors.HexColor("#CFE3D4")
WHITE = colors.white

PAGE_WIDTH = A4[0] - 4 * cm


def _text(value: object) -> str:
    return escape(str(value), {"'": "&apos;", '"': "&quot;"})


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "ZCoverTitle",
            parent=base["Heading1"],
            fontSize=25,
            leading=30,
            textColor=GREEN_DARK,
            spaceAfter=8,
            fontName="Helvetica-Bold",
        ),
        "cover_subtitle": ParagraphStyle(
            "ZCoverSubtitle",
            parent=base["Normal"],
            fontSize=12,
            leading=16,
            textColor=MUTED,
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "ZH1",
            parent=base["Heading1"],
            fontSize=16,
            leading=20,
            textColor=GREEN,
            spaceBefore=10,
            spaceAfter=7,
            fontName="Helvetica-Bold",
        ),
        "h2": ParagraphStyle(
            "ZH2",
            parent=base["Heading2"],
            fontSize=12,
            leading=15,
            textColor=GREEN_DARK,
            spaceBefore=7,
            spaceAfter=5,
            fontName="Helvetica-Bold",
        ),
        "h3": ParagraphStyle(
            "ZH3",
            parent=base["Heading3"],
            fontSize=10.5,
            leading=13,
            textColor=BLUE,
            spaceBefore=5,
            spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "ZBody",
            parent=base["Normal"],
            fontSize=9.4,
            leading=12.8,
            textColor=TEXT,
            alignment=TA_JUSTIFY,
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "ZSmall",
            parent=base["Normal"],
            fontSize=8,
            leading=10.2,
            textColor=MUTED,
            spaceAfter=3,
        ),
        "badge": ParagraphStyle(
            "ZBadge",
            parent=base["Normal"],
            fontSize=7.6,
            leading=9,
            textColor=GREEN_DARK,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        ),
        "code": ParagraphStyle(
            "ZCode",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.4,
            leading=9.5,
            textColor=colors.HexColor("#203326"),
        ),
        "table_cell": ParagraphStyle(
            "ZTableCell",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=TEXT,
        ),
        "table_head": ParagraphStyle(
            "ZTableHead",
            parent=base["Normal"],
            fontSize=8,
            leading=9.5,
            textColor=WHITE,
            fontName="Helvetica-Bold",
        ),
        "center": ParagraphStyle(
            "ZCenter",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=TEXT,
            alignment=TA_CENTER,
        ),
    }


def _p(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_text(text), style)


def _rich(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(GREEN_DARK)
    canvas.rect(0, A4[1] - 13 * mm, A4[0], 13 * mm, stroke=0, fill=1)
    canvas.setFillColor(YELLOW)
    canvas.rect(0, A4[1] - 13 * mm, 22 * mm, 13 * mm, stroke=0, fill=1)
    canvas.setFillColor(ORANGE)
    canvas.rect(22 * mm, A4[1] - 13 * mm, 8 * mm, 13 * mm, stroke=0, fill=1)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(2 * cm, A4[1] - 8.2 * mm, "ZCAMS")
    canvas.setFont("Helvetica", 7.5)
    canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 8.2 * mm, "Zambia Customs Agent Management System")
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.5)
    canvas.line(2 * cm, 14 * mm, A4[0] - 2 * cm, 14 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(2 * cm, 9 * mm, "ZCAMS documentation pack")
    canvas.drawRightString(A4[0] - 2 * cm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _doc(path: Path, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.1 * cm,
        bottomMargin=1.8 * cm,
        title=title,
        author="ZCAMS",
    )


def _section(title: str, styles: dict[str, ParagraphStyle]) -> list:
    table = Table(
        [[_rich(title, styles["h1"])]],
        colWidths=[PAGE_WIDTH],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), GREEN_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.55, GREEN),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        ),
    )
    return [Spacer(1, 3 * mm), table, Spacer(1, 3 * mm)]


def _cover(title: str, subtitle: str, audience: str, styles: dict[str, ParagraphStyle]) -> list:
    generated = datetime.now(timezone.utc).strftime("%d %B %Y %H:%M UTC")
    logo = Table(
        [[_rich("Z", styles["cover_title"]), _rich("<b>ZCAMS</b><br/>Zambia Customs Agent Management System", styles["body"])]],
        colWidths=[1.4 * cm, 13.5 * cm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), YELLOW),
                ("TEXTCOLOR", (0, 0), (0, 0), GREEN_DARK),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.6, GREEN),
                ("BACKGROUND", (1, 0), (1, 0), PANEL),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        ),
    )
    meta = Table(
        [
            ["Document", title],
            ["Audience", audience],
            ["Generated", generated],
            ["Theme", "ZCAMS green, gold, orange, and light operational panels"],
        ],
        colWidths=[3.4 * cm, 13.4 * cm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), GREEN_SOFT),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), GREEN_DARK),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BOX", (0, 0), (-1, -1), 0.55, GREEN),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, GRID),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        ),
    )
    return [
        Spacer(1, 10 * mm),
        logo,
        Spacer(1, 16 * mm),
        _p(title, styles["cover_title"]),
        _p(subtitle, styles["cover_subtitle"]),
        Spacer(1, 5 * mm),
        meta,
        Spacer(1, 10 * mm),
        _rich(
            "This document uses designed visual panels instead of live screenshots. The panels are intentionally "
            "high-level so they can be shared with users, ZAFFA stakeholders, and integration partners without "
            "exposing live operational data.",
            styles["body"],
        ),
        PageBreak(),
    ]


def _table(headers: list[str], rows: list[list[object]], widths: list[float] | None = None) -> Table:
    styles = _styles()
    data = [[_rich(f"<b>{_text(h)}</b>", styles["table_head"]) for h in headers]]
    data.extend([[_p(cell, styles["table_cell"]) for cell in row] for row in rows])
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.25, GRID),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PANEL]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _badge(text: str, color=GREEN_SOFT) -> Table:
    styles = _styles()
    badge = Table(
        [[_p(text, styles["badge"])]],
        colWidths=[3.6 * cm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("BOX", (0, 0), (-1, -1), 0.35, GREEN),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        ),
    )
    return badge


def _mock_screen(title: str, stats: list[tuple[str, str]], actions: list[str], note: str = "") -> Table:
    styles = _styles()
    stat_cells = []
    for label, value in stats[:3]:
        stat_cells.append(_rich(f"<b>{_text(value)}</b><br/><font color='#4A5D52'>{_text(label)}</font>", styles["center"]))
    while len(stat_cells) < 3:
        stat_cells.append("")
    action_rows = [[_rich(f"<b>{_text(action)}</b>", styles["table_cell"])] for action in actions[:4]]
    body = Table(
        [
            [
                _rich("<b>ZCAMS</b><br/>Customs Journey", styles["center"]),
                Table([stat_cells], colWidths=[3.2 * cm, 3.2 * cm, 3.2 * cm]),
            ],
            [_rich(f"<b>{_text(title)}</b>", styles["h2"]), _p(note or "Designed high-level screen panel", styles["small"])],
            [_rich("Main actions", styles["table_head"]), Table(action_rows or [["-"]], colWidths=[9.8 * cm])],
        ],
        colWidths=[4.6 * cm, 10.2 * cm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), GREEN_DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("BACKGROUND", (0, 1), (-1, -1), PANEL),
                ("BOX", (0, 0), (-1, -1), 0.6, GREEN),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        ),
    )
    return body


def _flow_strip(labels: list[str]) -> Table:
    styles = _styles()
    cells = []
    for index, label in enumerate(labels, start=1):
        cells.append(_rich(f"<b>{index}. {_text(label)}</b>", styles["center"]))
    table = Table([cells], colWidths=[PAGE_WIDTH / len(labels)] * len(labels))
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), GREEN_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.55, GREEN),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, GREEN),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _json_block(payload: dict) -> Table:
    styles = _styles()
    content = json.dumps(payload, indent=2)
    return Table(
        [[_rich("<br/>".join(_text(line) for line in content.splitlines()), styles["code"])]],
        colWidths=[PAGE_WIDTH],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FBF7")),
                ("BOX", (0, 0), (-1, -1), 0.35, GRID),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        ),
    )


MODULES = [
    {
        "name": "Login",
        "route": "/login",
        "roles": "All users",
        "purpose": "Secure entry point for Super Admin, Company Admin, and Declarant users.",
        "actions": ["Enter username or email", "Enter password", "Open role-based workspace"],
        "outcome": "The user lands on the correct dashboard with a professional session.",
    },
    {
        "name": "CFA Onboarding",
        "route": "/onboarding",
        "roles": "New CFA company",
        "purpose": "Register a clearing and forwarding company for ZAFFA review.",
        "actions": ["Capture company details", "Upload documents", "Create first admin account"],
        "outcome": "The company enters the approval queue for Super Admin review.",
    },
    {
        "name": "Dashboard",
        "route": "/dashboard",
        "roles": "All signed-in roles",
        "purpose": "Monitor BL, Z-SAD, invoice, payment, and release work.",
        "actions": ["Review metric cards", "Use quick actions", "Open Agentic Mode"],
        "outcome": "Users know what work requires attention.",
    },
    {
        "name": "BLs",
        "route": "/bls",
        "roles": "Declarant, Company Admin, Super Admin",
        "purpose": "Upload or capture Bills of Lading for customs processing.",
        "actions": ["Upload BL PDF", "Confirm extracted fields", "Select GN 83 category"],
        "outcome": "The BL is ready for review and Z-SAD generation.",
    },
    {
        "name": "Reviewed BL",
        "route": "/reviewed-bl",
        "roles": "Declarant, Company Admin, Super Admin",
        "purpose": "Issue and manage active Z-SAD records linked to reviewed BLs.",
        "actions": ["Review BL", "Issue Z-SAD", "Request invoice", "Release cargo"],
        "outcome": "The shipment has one active Z-SAD and can proceed to billing.",
    },
    {
        "name": "Invoices",
        "route": "/invoices",
        "roles": "Declarant, Company Admin, Super Admin",
        "purpose": "Track GN 83 invoices and payment settlement status.",
        "actions": ["Review invoice totals", "Download PDF", "Mark settled"],
        "outcome": "Payment state is clear and linked to cargo release rules.",
    },
    {
        "name": "Check-out",
        "route": "/checkout",
        "roles": "Declarant, Company Admin, Super Admin",
        "purpose": "Open or share CapitalPay checkout links.",
        "actions": ["Find awaiting invoice", "Open Pay Now", "Share payment link"],
        "outcome": "Importer or CFA can complete payment outside manual follow-up.",
    },
    {
        "name": "Contracts",
        "route": "/contracts",
        "roles": "Company Admin, Super Admin",
        "purpose": "Generate and manage contract documents with importers.",
        "actions": ["Create contract", "Send signing link", "Track signing status"],
        "outcome": "Commercial terms are documented and auditable.",
    },
    {
        "name": "Company Profile",
        "route": "/company-profile",
        "roles": "Company Admin, Super Admin",
        "purpose": "Maintain company details, documents, users, and certificates.",
        "actions": ["Update profile", "Manage documents", "Review users"],
        "outcome": "CFA profile remains current for compliance and integrations.",
    },
    {
        "name": "Notifications",
        "route": "/notifications",
        "roles": "All signed-in roles",
        "purpose": "Read system events for BLs, invoices, support, and approvals.",
        "actions": ["Review alerts", "Filter messages", "Follow up on events"],
        "outcome": "Users have a timeline of actions and required attention.",
    },
    {
        "name": "Support",
        "route": "/support",
        "roles": "All signed-in roles",
        "purpose": "Raise and monitor operational support tickets.",
        "actions": ["Create ticket", "Add details", "Track response"],
        "outcome": "Issues are captured with context for admin support.",
    },
    {
        "name": "ZCAMS Chat",
        "route": "/chat",
        "roles": "All signed-in roles",
        "purpose": "Ask workflow and GN 83 questions inside ZCAMS.",
        "actions": ["Ask a question", "Review guidance", "Use answer in workflow"],
        "outcome": "Users receive contextual help without leaving the platform.",
    },
    {
        "name": "GN 83 Schedule",
        "route": "/gn83",
        "roles": "All signed-in roles",
        "purpose": "Reference Gazette Notice fee rules and cargo categories.",
        "actions": ["Search categories", "Review minimum fees", "Confirm billing basis"],
        "outcome": "Invoice amounts align with the official fee schedule.",
    },
    {
        "name": "Company Admin",
        "route": "/admin",
        "roles": "Company Admin, Super Admin",
        "purpose": "Manage company users, oversight, compliance, and support tools.",
        "actions": ["Create users", "Review operations", "Use support tools"],
        "outcome": "Company-level governance is handled without platform access.",
    },
    {
        "name": "Super Admin",
        "route": "/super-admin",
        "roles": "Super Admin",
        "purpose": "Control platform-wide users, CFA registry, sessions, audit, and support.",
        "actions": ["Approve CFAs", "Manage all users", "Review transactions"],
        "outcome": "ZAFFA can monitor and govern the full ZCAMS platform.",
    },
    {
        "name": "Agentic Mode",
        "route": "Dashboard modal",
        "roles": "Declarant, Company Admin, Super Admin",
        "purpose": "Run a guided BL-to-Z-SAD-to-invoice workflow with human review.",
        "actions": ["Upload BL", "Confirm five values", "Generate Z-SAD and invoice"],
        "outcome": "The workflow completes faster while preserving human approval.",
    },
]


def build_system_modules_tutorial(output_path: Path | None = None) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = output_path or DOCS_DIR / "ZCAMS_System_Modules_Tutorial.pdf"
    styles = _styles()
    story: list = []
    story.extend(
        _cover(
            "ZCAMS System Modules Tutorial",
            "High-level guide to the main ZCAMS modules, roles, actions, and expected outcomes.",
            "ZAFFA, CFA company administrators, declarants, trainers, and support teams",
            styles,
        )
    )
    story.extend(_section("1. System Journey At A Glance", styles))
    story.append(
        _rich(
            "ZCAMS follows a controlled customs journey: <b>BL upload</b>, <b>reviewed BL</b>, "
            "<b>Z-SAD generation</b>, <b>GN 83 invoicing</b>, <b>CapitalPay checkout</b>, "
            "<b>payment settlement</b>, and <b>cargo release</b>.",
            styles["body"],
        )
    )
    story.append(_flow_strip(["Upload BL", "Review & Z-SAD", "Invoice", "Check-out", "Cargo Release"]))
    story.append(Spacer(1, 5 * mm))
    story.append(
        _table(
            ["Role", "Main responsibility", "Typical modules"],
            [
                ["Super Admin", "Platform governance across all CFA companies.", "Super Admin, Dashboard, BLs, Reviewed BL, Invoices, Admin, Chat, GN 83"],
                ["Company Admin", "Company-level users, profile, compliance, and operations.", "Admin, Company Profile, BLs, Reviewed BL, Invoices, Support"],
                ["Declarant / Agent", "Operational clearance work for one CFA company.", "Dashboard, BLs, Reviewed BL, Invoices, Check-out, Contracts, Chat"],
            ],
            [3.2 * cm, 6.3 * cm, 7.3 * cm],
        )
    )
    story.append(PageBreak())

    story.extend(_section("2. Module-by-Module Tutorial", styles))
    for index, module in enumerate(MODULES, start=1):
        block = [
            _rich(f"{index}. {_text(module['name'])}", styles["h2"]),
            Table(
                [
                    [_badge(str(module["route"]), GREEN_SOFT), _badge(str(module["roles"]), colors.HexColor("#FFF5D6"))],
                ],
                colWidths=[4.2 * cm, 4.2 * cm],
            ),
            Spacer(1, 2 * mm),
            _rich(f"<b>Purpose:</b> {_text(module['purpose'])}", styles["body"]),
            _rich(f"<b>Key actions:</b> {_text('; '.join(module['actions']))}.", styles["body"]),
            _rich(f"<b>Expected outcome:</b> {_text(module['outcome'])}", styles["body"]),
            _mock_screen(
                str(module["name"]),
                [("Route", str(module["route"])), ("Role scope", str(module["roles"])), ("Status", "Guided")],
                list(module["actions"]),
                str(module["purpose"]),
            ),
            Spacer(1, 4 * mm),
        ]
        story.append(KeepTogether(block))
    story.append(PageBreak())
    story.extend(_section("3. Trainer Notes", styles))
    story.append(
        _table(
            ["Training topic", "What to demonstrate", "Success signal"],
            [
                ["Role-based navigation", "Log in with each role and compare visible modules.", "Users understand why screens differ by role."],
                ["Workflow strip", "Move from BLs to Reviewed BL, Invoices, Check-out, and release.", "Users can follow the customs journey without guessing."],
                ["Notifications and audit", "Show how system events appear after actions.", "Users trust that actions are tracked."],
                ["Support and chat", "Raise a ticket and ask a ZCAMS Chat question.", "Users know where to get help."],
            ],
            [4.1 * cm, 7.0 * cm, 5.7 * cm],
        )
    )
    _doc(out, "ZCAMS System Modules Tutorial").build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return out


def build_zsad_invoice_tutorial(output_path: Path | None = None) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = output_path or DOCS_DIR / "ZCAMS_ZSAD_Invoice_Tutorial.pdf"
    styles = _styles()
    story: list = []
    story.extend(
        _cover(
            "ZCAMS Z-SAD And Invoice Tutorial",
            "How to generate a Z-SAD, create Full Settlement invoices, and complete payment flow.",
            "Declarants, Company Admins, Super Admins, support teams, and implementation trainers",
            styles,
        )
    )
    story.extend(_section("1. End-to-End Clearance Flow", styles))
    story.append(
        _rich(
            "The Z-SAD and invoice flow begins when a BL is uploaded or captured. ZCAMS reviews the BL, "
            "issues one active Z-SAD, calculates GN 83 charges, creates a CapitalPay invoice, and uses payment "
            "settlement rules to release cargo.",
            styles["body"],
        )
    )
    story.append(_flow_strip(["BL Upload", "Review BL", "Issue Z-SAD", "Invoice Type", "CapitalPay", "Release"]))
    story.append(Spacer(1, 4 * mm))
    story.append(
        _mock_screen(
            "Reviewed BL: Z-SAD And Invoice Controls",
            [("BL status", "Uploaded"), ("Z-SAD", "Ready"), ("Invoice", "Not generated")],
            ["Review & Issue Z-SAD", "Choose Full Settlement", "Choose Full Settlement", "Pay Now / Generate and Share"],
            "Designed panel showing the core controls used during Z-SAD and invoice generation.",
        )
    )
    story.append(PageBreak())

    story.extend(_section("2. Manual Z-SAD Generation", styles))
    story.append(
        _table(
            ["Step", "User action", "System result"],
            [
                ["1", "Open BLs and upload or capture the Bill of Lading.", "The BL is saved with route, transport, consignee, cargo, and GN 83 category fields."],
                ["2", "Open Reviewed BL and find the BL under awaiting review.", "The BL is ready for compliance review."],
                ["3", "Click Review & Issue Z-SAD.", "ZCAMS creates a reviewed BL record and one active Z-SAD number."],
                ["4", "Confirm the BL appears under Active Reviewed BLs.", "The record is ready for Full Settlement billing."],
                ["5", "Use Replace BL only if the document must be corrected.", "Old Z-SAD and open invoices are retired according to workflow rules."],
            ],
            [1.2 * cm, 7.2 * cm, 8.4 * cm],
        )
    )
    story.append(Spacer(1, 5 * mm))
    story.append(
        _rich(
            "<b>Important:</b> ZCAMS is designed around one active Z-SAD per reviewed BL. Superseded Z-SADs stay in history for audit.",
            styles["body"],
        )
    )

    story.extend(_section("3. Invoice Type Decision", styles))
    story.append(
        _table(
            ["Invoice type", "When to use it", "GN 83 calculation", "Release behavior"],
            [
                [
                    "Full Settlement",
                    "Use when the platform should collect the the full settlement amount.",
                    "Admin fee is 20% of the standard minimum. VAT is 16% on the admin fee only.",
                    "Payment moves the reviewed BL to release-pending; release can then be issued.",
                ],
                [
                    "Full Settlement",
                    "Use when the platform should collect the full customs settlement amount through the invoice.",
                    "Standard minimum + 20% admin fee + VAT on the combined subtotal.",
                    "Payment can complete the cargo release flow automatically.",
                ],
            ],
            [3.4 * cm, 4.6 * cm, 4.7 * cm, 4.1 * cm],
        )
    )

    story.extend(_section("4. Full Settlement Invoice", styles))
    story.append(
        _table(
            ["Step", "Action", "Expected outcome"],
            [
                ["1", "Click Full Settlement from the reviewed BL invoice action.", "The invoice modal opens with Agency Charge selected."],
                ["2", "Review the GN 83 minimum, admin fee, VAT, and total.", "The user understands the amount being charged."],
                ["3", "Enter importer email/phone if sharing is required.", "ZCAMS can send the invoice to the importer."],
                ["4", "Click Generate & Share Invoice or Pay Now.", "ZCAMS creates the invoice and CapitalPay reference."],
                ["5", "Settle the invoice after payment confirmation.", "Shipment moves toward cargo release."],
            ],
            [1.2 * cm, 7.1 * cm, 8.5 * cm],
        )
    )
    story.append(
        _mock_screen(
            "Full Settlement Invoice",
            [("Std minimum", "Informational"), ("Admin fee", "20%"), ("VAT", "16% of admin")],
            ["Review amount", "Generate & Share", "Pay Now", "Track settlement"],
            "Designed panel for the agency-charge workflow.",
        )
    )

    story.extend(_section("5. Full Settlement Invoice", styles))
    story.append(
        _table(
            ["Step", "Action", "Expected outcome"],
            [
                ["1", "Click Full Settlement from the reviewed BL invoice action.", "The invoice modal opens with beneficiary fields."],
                ["2", "Confirm the settlement amount is at least the GN 83 minimum.", "ZCAMS prevents under-billing."],
                ["3", "Enter beneficiary name, bank, and account number.", "The settlement instructions appear on the invoice PDF."],
                ["4", "Click Generate & Share Invoice or Pay Now.", "ZCAMS creates CapitalPay invoice and checkout link."],
                ["5", "Settle the invoice once payment is confirmed.", "Cargo release can complete automatically for the full settlement path."],
            ],
            [1.2 * cm, 7.1 * cm, 8.5 * cm],
        )
    )
    story.append(
        _mock_screen(
            "Full Settlement Invoice",
            [("Std amount", "Charged"), ("Admin", "20%"), ("VAT", "16% subtotal")],
            ["Enter beneficiary bank", "Confirm settlement", "Generate & Share", "Pay Now"],
            "Designed panel for the full-settlement workflow.",
        )
    )
    story.append(PageBreak())

    story.extend(_section("6. Agentic Mode Shortcut", styles))
    story.append(
        _rich(
            "Agentic Mode follows the same business rules but guides the user through upload, extraction, human validation, "
            "Z-SAD generation, invoice creation, Pay Now, and optional client sharing inside one modal.",
            styles["body"],
        )
    )
    story.append(
        _table(
            ["Checkpoint", "Human confirmation", "System action"],
            [
                ["Upload", "Confirm the selected BL file.", "OCR extracts available BL/customs fields."],
                ["Five values", "Confirm BL number, TIN, gross weight, cargo count, and invoice type.", "ZCAMS validates core workflow inputs."],
                ["Run workflow", "Approve the run after values are confirmed.", "BL, Z-SAD, and invoice are generated."],
                ["Pay / Share", "Click Pay Now or Approve and send to client.", "CapitalPay reference and amount are shown after the click."],
            ],
            [3.2 * cm, 6.1 * cm, 7.5 * cm],
        )
    )
    story.extend(_section("7. Operational Rules To Remember", styles))
    story.extend(
        [
            _rich("- Do not issue a new Z-SAD unless the BL genuinely needs correction or replacement.", styles["body"]),
            _rich("- Full Settlement invoices use different VAT bases.", styles["body"]),
            _rich("- Pay Now opens CapitalPay checkout; Generate & Share sends the invoice to the importer.", styles["body"]),
            _rich("- Payment status drives release status, so settlement should be updated carefully.", styles["body"]),
        ]
    )
    _doc(out, "ZCAMS Z-SAD And Invoice Tutorial").build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return out


API_ENDPOINTS = [
    {
        "method": "GET",
        "path": "/api/asycuda/v1/health",
        "purpose": "Confirm API availability and version compatibility.",
        "query": "None",
        "response": {"status": "ok", "system": "ZCAMS", "version": "v1", "timestamp": "2026-05-29T09:00:00Z"},
    },
    {
        "method": "GET",
        "path": "/api/asycuda/v1/declarations",
        "purpose": "Search ZCAMS declarations by Z-SAD, BL number, invoice number, company TPIN, or payment status.",
        "query": "z_sad, bl_number, invoice_number, company_tpin, status, payment_status, page, page_size",
        "response": {"items": [{"z_sad_number": "Z-SAD-3322-123456ABCDEF", "bl_number": "MSC4051473322", "invoice_status": "AWAITING_PAYMENT"}], "page": 1, "page_size": 25},
    },
    {
        "method": "GET",
        "path": "/api/asycuda/v1/declarations/{z_sad_number}",
        "purpose": "Return a complete declaration summary for one active or historical Z-SAD.",
        "query": "Path parameter only",
        "response": {"z_sad_number": "Z-SAD-3322-123456ABCDEF", "reviewed_status": "AWAITING_PAYMENT", "company_id": "company-zaffa-demo", "invoice_number": "INV-20260529120000-A1B2C3"},
    },
    {
        "method": "GET",
        "path": "/api/asycuda/v1/declarations/{z_sad_number}/company-profile",
        "purpose": "Share CFA company registration and compliance profile details linked to the declaration.",
        "query": "Path parameter only",
        "response": {"company": {"name": "ZAFFA Clearing & Forwarding", "tpin": "1000123456", "zra_licence": "ZRA-CFA-2026", "zaffa_number": "ZAFFA-001"}},
    },
    {
        "method": "GET",
        "path": "/api/asycuda/v1/declarations/{z_sad_number}/customs-details",
        "purpose": "Share parsed customs and shipment fields from the Bill of Lading.",
        "query": "Path parameter only",
        "response": {"bl_number": "MSC4051473322", "consignee_tin": "1000123456", "route_type": "IMPORT", "transport_mode": "SEA", "zra_regime": "IMPORT_HOME_USE"},
    },
    {
        "method": "GET",
        "path": "/api/asycuda/v1/declarations/{z_sad_number}/cargo",
        "purpose": "Share cargo line items, HS codes, weights, quantities, GN 83 category, and containers.",
        "query": "Path parameter only",
        "response": {"cargo_items": [{"description": "Motor vehicles", "hs_code": "8703", "weight": 12000, "gn83_category": "MOTOR_VEHICLE"}], "containers": [{"container_no": "MSCU1234567", "size": "40HC"}]},
    },
    {
        "method": "GET",
        "path": "/api/asycuda/v1/declarations/{z_sad_number}/invoice",
        "purpose": "Share the generated invoice, amount breakdown, CapitalPay reference, and PDF metadata.",
        "query": "Path parameter only",
        "response": {"invoice_number": "INV-20260529120000-A1B2C3", "invoice_type": "FULL_SETTLEMENT", "total": 181.0, "currency": "USD", "pdf_url": "https://zcams.info/download/invoice/inv-id.pdf"},
    },
    {
        "method": "GET",
        "path": "/api/asycuda/v1/declarations/{z_sad_number}/payment-status",
        "purpose": "Tell ASYCUDA whether the linked invoice has been paid and whether cargo can be released.",
        "query": "Path parameter only",
        "response": {"invoice_status": "SETTLED", "payment_status": "SETTLED", "settled_at": "2026-05-29T09:15:00Z", "release_status": "CARGO_RELEASED"},
    },
]


def build_asycuda_api_spec(output_path: Path | None = None) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = output_path or DOCS_DIR / "ZCAMS_ASYCUDA_API_Specification.pdf"
    styles = _styles()
    story: list = []
    story.extend(
        _cover(
            "ZCAMS ASYCUDA API Specification",
            "Proposed read-only integration endpoints for sharing Z-SAD, customs, company, invoice, and payment status data.",
            "ASYCUDA integration teams, ZAFFA platform owners, and ZCAMS engineers",
            styles,
        )
    )
    story.extend(_section("1. Integration Overview", styles))
    story.append(
        _rich(
            "This document proposes eight read-only API endpoints under <b>/api/asycuda/v1</b>. "
            "The goal is to allow ASYCUDA to retrieve the Z-SAD number, customs details parsed by the CFA, "
            "company profile information, generated invoice details, and whether the invoice is paid.",
            styles["body"],
        )
    )
    story.append(_flow_strip(["ZCAMS BL", "Z-SAD", "Invoice", "Payment", "ASYCUDA Query"]))
    story.append(Spacer(1, 4 * mm))
    story.append(
        _table(
            ["Security requirement", "Recommendation"],
            [
                ["Transport", "HTTPS only. Reject plain HTTP in production."],
                ["Authentication", "Server-to-server API key or signed bearer token issued by ZAFFA/ZCAMS."],
                ["Authorization", "Read-only scope: asycuda:read. No user password sharing."],
                ["Audit", "Log request id, endpoint, caller id, timestamp, query, and response status."],
                ["Data ownership", "ZCAMS remains source of operational CFA workflow; ASYCUDA consumes agreed declaration/payment data."],
            ],
            [4.4 * cm, 12.4 * cm],
        )
    )
    story.append(PageBreak())

    story.extend(_section("2. Proposed Endpoint Catalogue", styles))
    story.append(
        _table(
            ["#", "Method", "Endpoint", "Purpose"],
            [[str(i), ep["method"], ep["path"], ep["purpose"]] for i, ep in enumerate(API_ENDPOINTS, start=1)],
            [0.8 * cm, 1.6 * cm, 7.1 * cm, 7.3 * cm],
        )
    )
    story.append(PageBreak())

    story.extend(_section("3. Endpoint Details And Examples", styles))
    for index, ep in enumerate(API_ENDPOINTS, start=1):
        story.append(
            KeepTogether(
                [
                    _rich(f"{index}. {ep['method']} {_text(ep['path'])}", styles["h2"]),
                    _rich(f"<b>Purpose:</b> {_text(ep['purpose'])}", styles["body"]),
                    _rich(f"<b>Query parameters:</b> {_text(ep['query'])}", styles["body"]),
                    _rich("<b>Success response example:</b>", styles["h3"]),
                    _json_block(ep["response"]),
                    Spacer(1, 4 * mm),
                ]
            )
        )
    story.append(PageBreak())

    story.extend(_section("4. Common Response And Error Model", styles))
    story.append(
        _table(
            ["HTTP status", "Meaning", "Example use"],
            [
                ["200", "Success", "Declaration, invoice, cargo, or payment status returned."],
                ["400", "Bad request", "Invalid date, status, or malformed Z-SAD number."],
                ["401", "Unauthenticated", "Missing or invalid ASYCUDA API key/token."],
                ["403", "Forbidden", "Caller does not have asycuda:read scope."],
                ["404", "Not found", "Z-SAD, invoice, or company profile not found."],
                ["409", "Conflict", "Z-SAD exists but is retired/superseded and active-only data was requested."],
                ["429", "Rate limited", "Too many requests from the integration client."],
                ["500", "Server error", "Unexpected ZCAMS failure with request id for support tracing."],
            ],
            [2.2 * cm, 4.2 * cm, 10.4 * cm],
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(_rich("<b>Standard error body:</b>", styles["h3"]))
    story.append(
        _json_block(
            {
                "error": {
                    "code": "DECLARATION_NOT_FOUND",
                    "message": "No ZCAMS declaration was found for the supplied Z-SAD number.",
                    "request_id": "req_20260529_001",
                }
            }
        )
    )

    story.extend(_section("5. Future Write-Back Option", styles))
    story.append(
        _rich(
            "If ASYCUDA later needs to send processing acknowledgements into ZCAMS, add a separate authenticated "
            "write-back endpoint such as <b>POST /api/asycuda/v1/declarations/{z_sad_number}/acknowledgement</b>. "
            "That endpoint should persist ASYCUDA reference numbers, filing status, timestamps, and rejection reasons "
            "in a dedicated audit table before any UI status is changed.",
            styles["body"],
        )
    )
    _doc(out, "ZCAMS ASYCUDA API Specification").build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return out


def build_all() -> list[Path]:
    return [
        build_system_modules_tutorial(),
        build_zsad_invoice_tutorial(),
        build_asycuda_api_spec(),
    ]


def main() -> None:
    for path in build_all():
        print(path)


if __name__ == "__main__":
    main()
