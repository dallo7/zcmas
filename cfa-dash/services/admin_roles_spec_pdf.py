"""Generate ZCAMS Admin & Super Admin roles specification PDF."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
LOGO_PATH = ASSETS_DIR / "zcams-logo.png"

GREEN = colors.HexColor("#06451F")
GREEN_DARK = colors.HexColor("#063619")
MINT = colors.HexColor("#EAF6EC")
PANEL = colors.HexColor("#FBFEFB")
TEXT = colors.HexColor("#1A2E24")
MUTED = colors.HexColor("#4A5D52")
GOLD = colors.HexColor("#C9A227")
RED = colors.HexColor("#8B1E1E")
BLUE = colors.HexColor("#0033A0")


def _styles():
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=base["Heading1"],
            fontSize=24,
            leading=28,
            textColor=GREEN_DARK,
            spaceAfter=10,
            fontName="Helvetica-Bold",
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub",
            parent=base["Normal"],
            fontSize=12,
            leading=16,
            textColor=MUTED,
            spaceAfter=6,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontSize=16,
            leading=20,
            textColor=GREEN,
            spaceBefore=14,
            spaceAfter=8,
            fontName="Helvetica-Bold",
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontSize=12,
            leading=15,
            textColor=GREEN_DARK,
            spaceBefore=10,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "h3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontSize=10.5,
            leading=13,
            textColor=BLUE,
            spaceBefore=8,
            spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontSize=9.5,
            leading=13,
            textColor=TEXT,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontSize=9.5,
            leading=12.5,
            textColor=TEXT,
            leftIndent=14,
            bulletIndent=0,
            spaceAfter=3,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=MUTED,
            spaceAfter=4,
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontSize=8,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
    }


def _section_band(title: str, styles) -> list:
    return [
        Spacer(1, 4 * mm),
        Table(
            [[Paragraph(title, styles["h1"])]],
            colWidths=[16.8 * cm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), MINT),
                    ("BOX", (0, 0), (-1, -1), 0.5, GREEN),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            ),
        ),
        Spacer(1, 4 * mm),
    ]


def _table(headers: list[str], rows: list[list[str]], col_widths: list[float] | None = None):
    data = [headers] + rows
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CFE3D4")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _bullets(items: list[str], styles) -> list:
    return [Paragraph(f"• {item}", styles["bullet"]) for item in items]


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(GREEN)
    canvas.setLineWidth(2)
    canvas.line(2 * cm, A4[1] - 1.4 * cm, A4[0] - 2 * cm, A4[1] - 1.4 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(2 * cm, 1.2 * cm, "ZCAMS — Zambia Customs Agent Management System")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()


def build_admin_roles_spec_pdf(output_path: Path | None = None) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = output_path or (DOCS_DIR / "ZCAMS_Admin_And_Super_Admin_Roles.pdf")
    styles = _styles()
    story: list = []
    generated = datetime.now(timezone.utc).strftime("%d %B %Y %H:%M UTC")

    if LOGO_PATH.exists():
        story.append(Image(str(LOGO_PATH), width=3.2 * cm, height=3.2 * cm))
        story.append(Spacer(1, 6 * mm))

    story.extend(
        [
            Paragraph("ZCAMS Platform Governance", styles["cover_title"]),
            Paragraph("Super Admin &amp; Company Admin Roles, Modules, and Support Tooling", styles["cover_sub"]),
            Paragraph(
                "Specification aligned to the ZCAMS Plotly Dash POC architecture: CFA onboarding, "
                "Bill of Lading capture, Reviewed BL, Z-SAD, GN 83 invoicing, CapitalPay check-out, "
                "payment settlement, cargo release, contracts, certificates, notifications, and support.",
                styles["body"],
            ),
            Spacer(1, 4 * mm),
            Table(
                [
                    ["Document", "Admin & Super Admin Module Blueprint"],
                    ["Version", "1.0 (POC)"],
                    ["Generated", generated],
                    ["Audience", "ZAFFA platform owners, CFA company administrators, engineering"],
                ],
                colWidths=[4.5 * cm, 12.3 * cm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, -1), MINT),
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("BOX", (0, 0), (-1, -1), 0.5, GREEN),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CFE3D4")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                ),
            ),
            PageBreak(),
        ]
    )

    # 1. Executive summary
    story.extend(_section_band("1. Executive Summary", styles))
    story.append(
        Paragraph(
            "ZCAMS separates <b>platform governance</b> (Super Admin / ZAFFA) from "
            "<b>tenant administration</b> (Company Admin / CFA). Operational users "
            "(Declarant) execute clearance workflows but cannot change access policy. "
            "This document defines two dedicated dashboards, role assignment rules, "
            "permission boundaries, audit expectations, and five Admin support tools "
            "built from data already present in the ZCAMS SQLite schema.",
            styles["body"],
        )
    )

    # 2. Role model
    story.extend(_section_band("2. Role Model &amp; Assignment", styles))
    story.append(Paragraph("2.1 Standard roles", styles["h2"]))
    story.append(
        Paragraph(
            "<b>Declarant = Agent.</b> These are the same operational role in ZCAMS. "
            "The UI may show “Declarant / Agent”, but the stored role is <i>DECLARANT</i>. "
            "Legacy <i>AGENT</i> values are normalized automatically at login.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 2 * mm))
    story.append(
        _table(
            ["Role", "Also known as", "Scope", "Assigned by", "Primary purpose"],
            [
                [
                    "SUPER_ADMIN",
                    "—",
                    "Entire platform (all CFAs)",
                    "ZAFFA IT / bootstrap only",
                    "Approve CFAs, monitor all transactions, configure policies, audit everything",
                ],
                [
                    "COMPANY_ADMIN",
                    "—",
                    "Single CFA company",
                    "Super Admin or existing Company Admin",
                    "Manage company users, documents, and limited operational corrections",
                ],
                [
                    "DECLARANT",
                    "Agent",
                    "Single CFA company",
                    "Company Admin (within Super Admin limits)",
                    "Operational clearance workflow only — no admin or platform access",
                ],
            ],
            [2.4 * cm, 2.0 * cm, 2.8 * cm, 3.5 * cm, 6.1 * cm],
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("2.2 Role assignment rules", styles["h2"]))
    story.extend(
        _bullets(
            [
                "Super Admin accounts are created outside self-service onboarding and cannot be assigned by Company Admins.",
                "On CFA onboarding (<i>/onboarding</i>), the first user is created as COMPANY_ADMIN with company status PENDING_APPROVAL.",
                "Super Admin must approve the company (<i>approve_company</i>) before full workflow access is granted.",
                "Company Admin may create Declarant (Agent) users and additional COMPANY_ADMIN users only if Super Admin has enabled that privilege.",
                "At least one active COMPANY_ADMIN must remain per company; suspension/deletion of the last admin is blocked.",
                "Super Admin may suspend any user, reset passwords, reassign roles, and override Company Admin decisions.",
            ],
            styles,
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("2.3 Permission matrix (target state)", styles["h2"]))
    story.append(
        _table(
            ["Capability", "Super Admin", "Company Admin", "Declarant / Agent"],
            [
                ["View own company dashboard", "Yes (any company)", "Yes", "Yes"],
                ["View platform-wide dashboard", "Yes", "No", "No"],
                ["Approve CFA onboarding", "Yes", "No", "No"],
                ["Manage company profile & certificates", "Yes (all)", "Yes (own)", "Read only"],
                ["Create / suspend company users", "Yes (all)", "Yes (own, limited)", "No"],
                ["Upload & review BLs", "Yes (override)", "Yes", "Yes (operational only)"],
                ["Generate Z-SAD & GN 83 invoice", "Yes (override)", "Yes", "Yes (operational only)"],
                ["CapitalPay checkout & settlement view", "Yes (all)", "Yes (own)", "Yes (own workflow only)"],
                ["Issue cargo release", "Yes (override)", "Yes", "Yes (operational only)"],
                ["Contracts (create / sign oversight)", "Yes (all)", "Yes (own)", "As configured by admin"],
                ["View audit log", "Full platform", "Own company", "No"],
                ["View login / session history", "Full platform", "Own company users", "Self only"],
                ["Manage users or company documents", "Yes (all)", "Yes (own)", "No"],
                ["Access /admin or /super-admin modules", "Yes", "Yes (/admin only)", "No"],
                ["Change platform configuration", "Yes", "No", "No"],
                ["Support tickets — resolve escalations", "Yes (all)", "Own company", "Create only"],
            ],
            [5.5 * cm, 3.1 * cm, 3.6 * cm, 3.6 * cm],
        )
    )

    story.append(PageBreak())

    # 3. Super Admin module
    story.extend(_section_band("3. Super Admin Module (Platform Control Centre)", styles))
    story.append(
        Paragraph(
            "Route: <b>/super-admin</b> (dedicated shell; not shared with CFA operational nav). "
            "Super Admin receives full visibility across companies, users, workflow entities, "
            "and audit data stored in <i>zcams.db</i>.",
            styles["body"],
        )
    )
    story.append(Paragraph("3.1 Super Admin dashboard widgets", styles["h2"]))
    story.extend(
        _bullets(
            [
                "Pending CFA approvals — companies with status PENDING_APPROVAL (from <i>companies</i>).",
                "Active CFAs & compliance score — approved companies with certificate completeness.",
                "Live workflow pipeline — counts for BLs, Reviewed BLs, Z-SADs, outstanding invoices, settled payments, releases.",
                "Today's activity — latest <i>audit_events</i> and <i>notifications</i> across all tenants.",
                "Open support escalations — <i>support_tickets</i> with priority High / status Open.",
                "Login activity — who signed in, when, from which IP (requires login audit enhancement).",
            ],
            styles,
        )
    )
    story.append(Paragraph("3.2 Super Admin sub-modules", styles["h2"]))
    modules = [
        (
            "CFA Registry & Onboarding Queue",
            "/super-admin/companies",
            "List all companies; open onboarding packet (PACRA, TPIN, ZRA licence, certificates); "
            "Approve, reject, or suspend; trigger credential email to Company Admin.",
        ),
        (
            "Global User & Role Governance",
            "/super-admin/users",
            "Search users across tenants; assign SUPER_ADMIN, COMPANY_ADMIN, DECLARANT (Agent); "
            "suspend/activate; reset passwords; define permission templates per Company Admin.",
        ),
        (
            "Platform Audit Log",
            "/super-admin/audit",
            "Immutable view of <i>audit_events</i>: BL uploads, Z-SAD generation, invoice creation, "
            "payments, cargo release, profile edits, user CRUD, company approval. Filter by company, "
            "user, action_type, date. Export CSV.",
        ),
        (
            "Login & Session Monitor",
            "/super-admin/sessions",
            "New table recommended: <i>login_events</i> (user_id, timestamp, ip, user_agent, success). "
            "Super Admin sees failed attempts, concurrent sessions, and forced logout.",
        ),
        (
            "Transaction Monitor",
            "/super-admin/transactions",
            "Cross-tenant timeline: BL → Reviewed BL → Z-SAD → Invoice → Payment → Cargo Release. "
            "Drill-down to entity; Super Admin may correct status (with mandatory audit reason).",
        ),
        (
            "Invoices & CapitalPay Oversight",
            "/super-admin/invoices",
            "All invoices and checkout URLs; retry CapitalPay signing; mark settled manually in exception cases.",
        ),
        (
            "Contracts & Compliance",
            "/super-admin/contracts",
            "Cross-company contract register; signature status; certificate expiry alerts.",
        ),
        (
            "Notifications & Broadcast",
            "/super-admin/notifications",
            "Platform-wide feed; send maintenance or policy broadcasts to all CFAs.",
        ),
        (
            "Support Command Centre",
            "/super-admin/support",
            "All tickets; assign to ZAFFA agent; link to BL/invoice; close with resolution code.",
        ),
        (
            "Platform Settings",
            "/super-admin/settings",
            "GN 83 parameters, CapitalPay mode, OCR provider, email templates, feature flags, "
            "Company Admin permission caps.",
        ),
    ]
    for name, route, desc in modules:
        story.append(Paragraph(f"{name} — <font color='#0033A0'>{route}</font>", styles["h3"]))
        story.append(Paragraph(desc, styles["body"]))

    story.append(PageBreak())

    # 4. Company Admin module
    story.extend(_section_band("4. Company Admin Module (Tenant Administration)", styles))
    story.append(
        Paragraph(
            "Route: <b>/admin</b> (Company Admin dashboard; distinct from operational <i>/dashboard</i>). "
            "Company Admin manages access and company-side documents within limits set by Super Admin. "
            "They do not see other CFAs unless explicitly granted a cross-tenant support role.",
            styles["body"],
        )
    )
    story.append(Paragraph("4.1 Company Admin dashboard widgets", styles["h2"]))
    story.extend(
        _bullets(
            [
                "Company compliance — profile completeness, certificates on file, banking details.",
                "Team overview — active/suspended users by role (from <i>users</i>).",
                "Workflow health (company-scoped) — pending BLs, invoices awaiting payment, releases pending.",
                "Recent company audit — last 20 <i>audit_events</i> for this company_id.",
                "Open support tickets raised by the company.",
            ],
            styles,
        )
    )
    story.append(Paragraph("4.2 Company Admin sub-modules", styles["h2"]))
    admin_modules = [
        (
            "Access Control",
            "/admin/access",
            "Create Declarants; promote to Company Admin if allowed; suspend users; "
            "cannot create Super Admin; cannot exceed Super Admin permission template.",
        ),
        (
            "Company Profile & Banking",
            "/admin/company",
            "Edit company details, logo, contact channels, bank account for invoice beneficiary fields.",
        ),
        (
            "Certificates & Documents",
            "/admin/certificates",
            "Upload/replace PACRA, TPIN, ZRA licence, agency certificates; "
            "Super Admin may lock documents after verification.",
        ),
        (
            "Operational Oversight (read + limited edit)",
            "/admin/operations",
            "Company-scoped BL, Reviewed BL, invoice list; correct OCR fields; "
            "re-upload BL when permitted; cannot delete settled financial records.",
        ),
        (
            "Contracts Administration",
            "/admin/contracts",
            "Create contracts, resend OTP, track signature status for importers.",
        ),
        (
            "Notifications & Alerts",
            "/admin/notifications",
            "Company notification feed; mark read; configure email preferences.",
        ),
        (
            "Support & Customer Service Tools",
            "/admin/tools",
            "Five operational tools (Section 6) for call-centre support.",
        ),
    ]
    for name, route, desc in admin_modules:
        story.append(Paragraph(f"{name} — <font color='#0033A0'>{route}</font>", styles["h3"]))
        story.append(Paragraph(desc, styles["body"]))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("4.3 Limits imposed by Super Admin", styles["h2"]))
    story.extend(
        _bullets(
            [
                "Maximum number of Company Admins and Declarants per CFA.",
                "Whether Company Admin may edit certificates after ZAFFA verification.",
                "Whether Company Admin may cancel/re-upload BLs after Z-SAD issuance.",
                "Whether Company Admin may manually mark invoices as settled (normally CapitalPay only).",
                "Whether Agentic Mode auto-send to clients is allowed without human approval.",
                "Module visibility (e.g. hide GN 83 schedule, disable chat model).",
            ],
            styles,
        )
    )

    story.append(PageBreak())

    # 5. Audit & security
    story.extend(_section_band("5. Audit, Login Tracking & Security Requirements", styles))
    story.append(Paragraph("5.1 Current POC gaps to close", styles["h2"]))
    story.extend(
        _bullets(
            [
                "Auth is client-side (dcc.Store in localStorage) — production needs server sessions or JWT.",
                "<i>audit_events.user_id</i> often defaults to demo user — must record acting user on every mutation.",
                "<i>ip_address</i> column exists but is not populated — capture on login and sensitive actions.",
                "No role checks on most callbacks — enforce RBAC middleware before page render and on every write.",
                "Download routes for invoices/documents are unauthenticated — protect with signed URLs.",
            ],
            styles,
        )
    )
    story.append(Paragraph("5.2 Recommended audit actions (minimum)", styles["h2"]))
    story.append(
        _table(
            ["Action type", "Entity", "Logged fields"],
            [
                ["USER_LOGIN / USER_LOGOUT", "users", "user_id, ip, timestamp, success/failure"],
                ["COMPANY_APPROVED", "companies", "approver_id, company_id, previous/new status"],
                ["BL_UPLOADED / BL_REVIEWED", "bills_of_lading", "bl_id, bl_number, actor"],
                ["ZSAD_GENERATED / ZSAD_DETACHED", "z_sads", "z_sad_number, reviewed_bl_id"],
                ["INVOICE_GENERATED / INVOICE_SETTLED", "invoices", "invoice_number, amounts, CapitalPay ref"],
                ["CARGO_RELEASED", "reviewed_bls", "reviewed_bl_id, bl_number"],
                ["USER_CREATED / USER_SUSPENDED", "users", "target user, role, actor"],
                ["CERTIFICATE_UPLOADED", "certificates", "document name, company_id"],
                ["ADMIN_OVERRIDE", "any", "reason text (mandatory for Super Admin corrections)"],
            ],
            [4.5 * cm, 3.5 * cm, 8.8 * cm],
        )
    )

    story.append(PageBreak())

    # 6. Admin support tools
    story.extend(_section_band("6. Company Admin Support Tooling (Customer Service)", styles))
    story.append(
        Paragraph(
            "These five tools use existing ZCAMS tables and integrations. Each is designed for a "
            "typical customer-service call: the Admin enters one identifier (BL number, invoice number, "
            "email, or company name) and receives an actionable answer within seconds.",
            styles["body"],
        )
    )

    tools = [
        (
            "Tool 1 — Shipment & Clearance Tracker",
            "Customer says: “Where is my cargo? Has customs cleared it?”",
            "Data sources: bills_of_lading, reviewed_bls, z_sads, invoices, payments, notifications.",
            [
                "Single search by BL number, Z-SAD number, or invoice number.",
                "Visual pipeline: Uploaded → Reviewed → Z-SAD issued → Invoice sent → Payment settled → Cargo released.",
                "Shows timestamps, responsible user (from audit_events), and blockers (e.g. unpaid invoice).",
                "One-click copy of status summary for email/WhatsApp to client.",
            ],
        ),
        (
            "Tool 2 — Payment & CapitalPay Resolver",
            "Customer says: “I paid but the portal still shows outstanding” or “The checkout link expired.”",
            "Data sources: invoices, payments, CapitalPay URN/checkout_url, notifications.",
            [
                "Lookup invoice by INV number or BL; show GN 83 breakdown (std min fee, admin fee, VAT, total).",
                "Display CapitalPay status, secure link, due date, and last settlement attempt.",
                "Flag mismatch between payable_amount and CapitalPay checkout total.",
                "Actions (if permitted): resend checkout link, refresh CapitalPay session, escalate to Super Admin.",
            ],
        ),
        (
            "Tool 3 — User Access & Login Diagnostic",
            "Customer says: “I cannot log in” or “My declarant account is locked.”",
            "Data sources: users, companies, audit_events, login_events (new).",
            [
                "Search by email or username; show role, status (ACTIVE/SUSPENDED), company affiliation.",
                "Show last successful login, failed attempts, and whether company is still PENDING_APPROVAL.",
                "Actions: trigger password reset email, unsuspend (within policy), verify demo vs production account.",
            ],
        ),
        (
            "Tool 4 — Document & Certificate Completeness Check",
            "Customer says: “Onboarding is stuck” or “We cannot generate invoices — missing documents.”",
            "Data sources: companies, certificates, company profile fields, compliance_score logic.",
            [
                "Checklist: PACRA, TPIN, ZRA licence, bank details, logo, signed contract status.",
                "Highlight missing or unverified certificates blocking approval or invoicing.",
                "Show upload date and who uploaded; link to /admin/certificates to fix.",
            ],
        ),
        (
            "Tool 5 — Invoice Dispute & GN 83 Fee Explainer",
            "Customer says: “This fee is wrong” or “Why is VAT different from what I expected?”",
            "Data sources: cargo_items (gn83_category), gn83.py rates, invoices, bills_of_lading.",
            [
                "Recalculate GN 83 from stored cargo category, weight, and containers.",
                "Side-by-side: system calculation vs issued invoice; explain admin fee (20%) and VAT (16%).",
                "Show Gazette Notice category mapping and minimum fee USD for the cargo type.",
                "Export PDF fee breakdown for client dispute resolution (reuse pdf_service styling).",
            ],
        ),
    ]

    for title, complaint, sources, features in tools:
        story.append(Paragraph(title, styles["h2"]))
        story.append(Paragraph(f"<i>Typical complaint:</i> {complaint}", styles["body"]))
        story.append(Paragraph(f"<b>Data sources:</b> {sources}", styles["small"]))
        story.extend(_bullets(features, styles))
        story.append(Spacer(1, 2 * mm))

    story.append(PageBreak())

    # 7. Implementation roadmap
    story.extend(_section_band("7. Implementation Roadmap (POC → Production)", styles))
    story.append(
        _table(
            ["Phase", "Deliverables", "Priority"],
            [
                ["Phase 1", "RBAC middleware; login_events table; fix audit user_id; /super-admin shell", "Critical"],
                ["Phase 2", "CFA approval UI; platform audit log; transaction monitor", "High"],
                ["Phase 3", "/admin dashboard; access control UI; certificate admin", "High"],
                ["Phase 4", "Five CS support tools on /admin/tools", "Medium"],
                ["Phase 5", "Permission templates; server sessions; secured downloads", "Medium"],
            ],
            [2.5 * cm, 10.3 * cm, 3 * cm],
        )
    )

    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "<b>Summary:</b> Super Admin owns the platform — approvals, global visibility, audit, "
            "and policy. Company Admin owns the CFA tenant — users, documents, and customer-service "
            "tools within Super Admin limits. Declarants (Agents) execute operational clearance "
            "workflows only and cannot access admin modules. "
            "Implementing these modules closes the current gap where all roles share the same "
            "operational dashboard without enforced permissions.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 6 * mm))
    story.append(
        Paragraph(
            "© ZAFFA Clearing &amp; Forwarding — ZCAMS POC. For internal planning and EC2 deployment alignment.",
            styles["footer"],
        )
    )

    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="ZCAMS Admin and Super Admin Roles",
        author="ZCAMS Platform",
    )
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return out


if __name__ == "__main__":
    path = build_admin_roles_spec_pdf()
    print(f"Generated: {path}")
