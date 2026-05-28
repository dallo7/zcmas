from dash import dcc, html

from components.agentic_mode import agentic_button
from components.icons import icon
from components.workflow import breadcrumb, counts_for_nav, nav_badge, workflow_strip


PRIMARY_NAV = [
    ("/dashboard", "material-symbols:dashboard-outline-rounded", "Dashboard"),
    ("/bls", "lucide:file-up", "BLs"),
    ("/reviewed-bl#active-reviewed-bls", "lucide:file-check-2", "Reviewed BL"),
    ("/invoices", "lucide:receipt", "Invoices"),
    ("/checkout", "lucide:credit-card", "Check-out"),
    ("/contracts", "lucide:file-signature", "Contracts"),
    ("/company-profile", "lucide:building-2", "Company Profile"),
]

DECLARANT_NAV = [
    ("/dashboard", "material-symbols:dashboard-outline-rounded", "Dashboard"),
    ("/bls", "lucide:file-up", "BLs"),
    ("/reviewed-bl#active-reviewed-bls", "lucide:file-check-2", "Reviewed BL"),
    ("/invoices", "lucide:receipt", "Invoices"),
    ("/checkout", "lucide:credit-card", "Check-out"),
    ("/contracts", "lucide:file-signature", "Contracts"),
]

SUPER_ADMIN_NAV = [
    ("/super-admin", "lucide:shield-check", "Platform Control"),
    ("/super-admin#users", "lucide:users-round", "User Management"),
    ("/super-admin#companies", "lucide:building", "CFA Registry"),
    ("/super-admin#sessions", "lucide:monitor", "Sessions & Logins"),
    ("/super-admin#audit", "lucide:scroll-text", "Audit Log"),
    ("/super-admin#transactions", "lucide:git-branch", "Transactions"),
    ("/super-admin#support", "lucide:headphones", "Support"),
]

ADMIN_HUB_NAV = [
    ("/admin", "lucide:settings", "Company Admin"),
    ("/admin#tools", "lucide:wrench", "Support Tools"),
]

SECONDARY_NAV = [
    ("/notifications", "lucide:bell", "Notifications"),
    ("/support", "lucide:headphones", "Support"),
    ("/chat", "lucide:message-circle", "ZCAMS Chat"),
    ("/gn83", "lucide:file-star", "GN 83 Schedule"),
]

SUPER_ADMIN_TOOLS_NAV = [
    ("/chat", "lucide:message-circle", "ZCAMS Chat"),
    ("/gn83", "lucide:file-star", "GN 83 Schedule"),
]

TENANT = {
    "code": "Z",
    "name": "ZAFFA Clearing & Forwarding",
    "role": "Clearing Agent",
}

DEMO_USER = {
    "initials": "AZ",
    "name": "Admin",
    "email": "admin@zaffa.co.zm",
    "company": TENANT["name"],
    "role": TENANT["role"],
}


def display_user(user: dict | None = None) -> dict:
    if not user:
        return DEMO_USER
    first = user.get("first_name") or "ZCAMS"
    last = user.get("last_name") or "User"
    role_key = (user.get("role") or "COMPANY_ADMIN").upper()
    if role_key == "DECLARANT":
        role = "Declarant / Agent"
    else:
        role = role_key.replace("_", " ").title()
    initials = f"{first[:1]}{last[:1]}".upper()
    is_super_admin = role_key == "SUPER_ADMIN"
    company_name = user.get("company_name")
    if not company_name and user.get("company_id"):
        from services import repository

        company_name = (repository.get_company(user["company_id"]) or {}).get("name")
    tenant_name = "ZCAMS Administration" if is_super_admin else (company_name or TENANT["name"])
    return {
        "initials": initials,
        "name": f"{first} {last}",
        "email": user.get("email") or DEMO_USER["email"],
        "company": "ZCAMS Super Admin Console" if is_super_admin else (company_name or TENANT["name"]),
        "role": role,
        "tenant_name": tenant_name,
        "tenant_role": "Platform Oversight" if is_super_admin else TENANT["role"],
        "tenant_code": "SA" if is_super_admin else TENANT["code"],
    }


def nav_items_for_user(user: dict | None) -> tuple[list, list, list]:
    """Return primary nav, admin section label items, secondary nav for the signed-in role."""
    role = (user or {}).get("role", "COMPANY_ADMIN").upper()
    if role == "SUPER_ADMIN":
        return [
            *SUPER_ADMIN_NAV,
            ("/dashboard", "material-symbols:dashboard-outline-rounded", "Dashboard"),
            ("/bls", "lucide:file-up", "BLs"),
            ("/reviewed-bl#active-reviewed-bls", "lucide:file-check-2", "Reviewed BL"),
            ("/invoices", "lucide:receipt", "Invoices"),
            ("/checkout", "lucide:credit-card", "Check-out"),
            ("/contracts", "lucide:file-signature", "Contracts"),
            ("/company-profile", "lucide:building-2", "Company Profile"),
        ], ADMIN_HUB_NAV, SUPER_ADMIN_TOOLS_NAV
    if role == "DECLARANT":
        return DECLARANT_NAV, [], SECONDARY_NAV
    return PRIMARY_NAV, ADMIN_HUB_NAV, SECONDARY_NAV


PAGE_TUTORIALS = {
    "Dashboard": {
        "objective": "Monitor your company's live BL, Z-SAD, invoice, payment, and release work.",
        "steps": [
            "Review the metric cards for BLs, reviewed BLs, active Z-SADs, invoices, and settled payments.",
            "Use the quick actions to jump into the next operational task.",
            "Check Operational Updates for unread events, pending BL reviews, active Z-SADs, checkout work, and outstanding invoices.",
            "Use Agentic Mode when you want the guided BL-to-invoice workflow.",
            "Read Recent Notifications to confirm the latest system events.",
        ],
        "outcome": "You know what needs attention and can continue shipment processing without admin-only approval actions.",
    },
    "Agentic Mode": {
        "objective": "Let ZCAMS guide a BL through extraction, validation, Z-SAD, invoice, and client sharing steps.",
        "steps": [
            "Open Agentic Mode from the Dashboard header.",
            "Upload the BL and wait for the extraction progress to complete.",
            "Confirm the five critical values: BL number, consignee TIN, gross weight, cargo/container count, and Service Fee or Full Settlement.",
            "Enter the client email and phone number before running the workflow.",
            "Run Agentic Workflow and watch the milestones until the invoice is generated and shared.",
        ],
        "outcome": "The BL-to-invoice journey is completed with visible checkpoints and client notification.",
    },
    "BLs": {
        "objective": "Capture or upload a Bill of Lading so it can enter the Z-SAD workflow.",
        "steps": [
            "Enter the BL number, route type, transport mode, and ZRA regime.",
            "Add shipper, carrier, origin, destination, consignee, and cargo details.",
            "Select the GN 83 cargo category so the minimum fee can be calculated.",
            "Submit the BL record and confirm it appears in the uploaded BL list.",
            "Open Reviewed BL when the document is ready for compliance review.",
        ],
        "outcome": "The BL is saved and ready for review, Z-SAD generation, and invoicing.",
    },
    "Reviewed BL": {
        "objective": "Create a Z-SAD from an uploaded BL, manage the active Z-SAD, replace the BL when corrections are needed, and prepare payment.",
        "steps": [
            "Open Reviewed BL after a BL has been uploaded and saved.",
            "Find the BL in the awaiting review table and click Review & Issue Z-SAD.",
            "Confirm the BL appears in Active Reviewed BLs with one single-use active Z-SAD.",
            "Choose Service or Full Settlement to request the correct GN 83 invoice.",
            "Use Replace BL only when the current BL journey must be retired and uploaded again.",
            "Issue cargo release only after payment settlement rules are met.",
        ],
        "outcome": "The active page refreshes, the BL has one active Z-SAD, superseded Z-SADs stay in history, and billing can continue.",
    },
    "Invoices": {
        "objective": "Create and settle GN 83-compliant invoices linked to reviewed BLs.",
        "steps": [
            "Confirm the reviewed BL and Z-SAD are correct before billing.",
            "Choose Full Settlement or Service Fee Only based on the payment scenario.",
            "Let ZCAMS calculate minimum fee, admin fee, VAT, and total.",
            "Use the generated invoice record for payment follow-up.",
            "Mark the invoice as settled once payment is confirmed.",
        ],
        "outcome": "The invoice status reflects payment progress and can trigger cargo release logic.",
    },
    "Check-out": {
        "objective": "Share secure CapitalPay payment links with the CFA or importer.",
        "steps": [
            "Find the invoice awaiting payment.",
            "Review the invoice amount, Z-SAD, and checkout link.",
            "Open the CapitalPay checkout link for direct payment.",
            "Use WhatsApp sharing to send the secure link to the payer.",
            "Return to Invoices after settlement to confirm status.",
        ],
        "outcome": "The payer receives the correct secure payment link and can complete payment.",
    },
    "Contracts": {
        "objective": "Create importer contracts and track signature status.",
        "steps": [
            "Enter importer name, phone, email, and contract terms.",
            "Create the contract record and verify the generated contract number.",
            "Share the contract link through WhatsApp when needed.",
            "Mark the contract as signed after importer acceptance.",
            "Keep the contract list as the operational record.",
        ],
        "outcome": "Importer agreements are recorded and ready to support shipment processing.",
    },
    "Company Profile": {
        "objective": "Review ZAFFA company details and compliance completeness.",
        "steps": [
            "Check company registration details, TPIN, ZRA licence, and contact information.",
            "Review address and banking details for completeness.",
            "Inspect the compliance score for missing information.",
            "Upload missing company documents directly from the Company Profile page if needed.",
            "Use this page before approving or auditing a CFA.",
        ],
        "outcome": "You understand whether the company profile is ready for operational use.",
    },
    "Notifications": {
        "objective": "Track system events across onboarding, BLs, Z-SADs, invoices, and payments.",
        "steps": [
            "Open the notification list to see latest system activity.",
            "Scan event names to identify the module involved.",
            "Read the message for the exact action taken.",
            "Use the related module to continue the workflow if follow-up is required.",
            "Treat notifications as the audit-friendly activity feed.",
        ],
        "outcome": "You can quickly reconstruct what changed and what needs action.",
    },
    "Support": {
        "objective": "Raise and track support issues connected to any ZCAMS module.",
        "steps": [
            "Enter a clear support subject.",
            "Describe the issue and select the linked module.",
            "Choose the priority based on operational impact.",
            "Submit the ticket and confirm it appears in the list.",
            "Update the ticket status as the issue progresses.",
        ],
        "outcome": "Operational problems are recorded, prioritized, and trackable. ZCAMS human support call or WhatsApp: +25479008080.",
    },
    "ZCAMS Chat": {
        "objective": "Ask guided questions about ZCAMS workflows, GN 83, BL review, Z-SADs, and payments.",
        "steps": [
            "Type a focused question about the task you are trying to complete.",
            "Ask about GN 83 rules, Z-SAD handling, invoices, Check-out, or cargo release.",
            "Use the response as operational guidance inside the POC.",
            "If the question is outside the assistant scope, raise a Support ticket.",
            "Keep sensitive importer or cargo data out of general questions unless needed.",
        ],
        "outcome": "You receive quick workflow guidance without leaving the system.",
    },
    "GN 83 Schedule": {
        "objective": "Look up the minimum agency fee schedule used by invoice calculations.",
        "steps": [
            "Choose the route type: Import, Export, or Transit.",
            "Find the transport mode: Sea/Inland Waterways, Road, or Air.",
            "Match the cargo description to the correct tariff category.",
            "Check the unit of measure and minimum fee.",
            "Use the fee category consistently when creating BL cargo records.",
        ],
        "outcome": "The correct GN 83 minimum fee is applied before invoicing.",
    },
}


NAV_BADGE_KEYS = {
    "/bls": "bls_pending",
    "/reviewed-bl#active-reviewed-bls": "reviewed_invoice_ready",
    "/invoices": "outstanding_invoices",
    "/checkout": "checkout_pending",
    "/notifications": "notifications_unread",
}


def sidebar(pathname: str = "/dashboard", user: dict | None = None):
    display = display_user(user)
    role = (user or {}).get("role", "COMPANY_ADMIN").upper()
    company_id = None if role == "SUPER_ADMIN" else (user or {}).get("company_id")
    counts = counts_for_nav(company_id)
    primary_nav, admin_nav, secondary_nav = nav_items_for_user(user)

    def nav_link(href: str, icon_name: str, label: str):
        base_href = href.split("#", 1)[0]
        current = pathname or ""
        current_base, current_hash = (current.split("#", 1) + [""])[:2]
        if "#" in href:
            is_active = current == href
        elif current_hash:
            is_active = False
        else:
            is_active = current_base == base_href
        badge_key = NAV_BADGE_KEYS.get(href)
        badge_el = nav_badge(counts.get(badge_key, 0)) if badge_key else None
        return dcc.Link(
            [
                icon(icon_name, 15),
                html.Span(label, className="nav-link-label"),
                badge_el,
            ],
            href=href,
            className=f"nav-link{' active' if is_active else ''}",
        )

    return html.Aside(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Img(
                                src="/assets/zcams-logo.png",
                                className="brand-logo",
                                alt="ZCAMS Zambia Customs Agent Management System",
                            ),
                        ],
                        className="brand-logo-card",
                    ),
                    html.Div(
                        [
                            html.Div(display["tenant_code"], className="company-avatar super-admin-avatar" if user and user.get("role") == "SUPER_ADMIN" else "company-avatar"),
                            html.Div(
                                [
                                    html.Div(display["tenant_name"], style={"fontSize": "12px", "fontWeight": 620}),
                                    html.Div(display["tenant_role"], style={"fontSize": "10px", "color": "rgba(255,255,255,0.42)"}),
                                ],
                                style={"minWidth": 0, "flex": 1},
                            ),
                            icon("lucide:chevron-down", 12, color="rgba(255,255,255,0.28)"),
                        ],
                        className="company-switcher",
                    ),
                ],
                className="sidebar-header",
            ),
            html.Nav(
                [
                    *[nav_link(*item) for item in primary_nav],
                    *(
                        [
                            html.Div("Administration", className="nav-section-label"),
                            *[nav_link(*item) for item in admin_nav],
                        ]
                        if admin_nav
                        else []
                    ),
                    html.Div("Tools", className="nav-section-label"),
                    *[nav_link(*item) for item in secondary_nav],
                ],
                className="sidebar-nav",
            ),
            html.Div(
                html.Div(
                    [
                        html.Div(display["initials"], className="user-avatar super-admin-avatar" if user and user.get("role") == "SUPER_ADMIN" else "user-avatar"),
                        html.Div(
                            [
                                html.Div(display["name"], style={"fontSize": "12px", "fontWeight": 620, "color": "rgba(255,255,255,0.88)"}),
                                html.Div(display["email"], style={"fontSize": "10px", "color": "rgba(255,255,255,0.42)"}),
                            ],
                            style={"minWidth": 0, "flex": 1},
                        ),
                        dcc.Link(icon("lucide:log-out", 14, color="rgba(255,255,255,0.50)"), href="/logout", className="logout-link", title="Sign out"),
                    ],
                    className="user-card",
                ),
                className="sidebar-footer",
            ),
        ],
        className="sidebar",
    )


def module_help(title: str, text: str):
    tutorial = PAGE_TUTORIALS.get(title)
    if tutorial:
        content = [
            html.H4(title),
            html.P(text.rstrip(".") + ".", className="help-intro help-summary"),
            html.Div(
                [
                    html.Span("Goal", className="help-label help-label-goal"),
                    html.P(tutorial["objective"], className="help-objective"),
                ],
                className="help-section help-section-goal",
            ),
            html.Div(
                [
                    html.Span("Steps", className="help-label help-label-steps"),
                    html.Ol(
                        [
                            html.Li(
                                [
                                    html.Span(str(index), className="help-step-number"),
                                    html.Span(step, className="help-step-copy"),
                                ]
                            )
                            for index, step in enumerate(tutorial["steps"], start=1)
                        ],
                        className="help-steps",
                    ),
                ],
                className="help-section help-section-steps",
            ),
            html.Div(
                [
                    html.Span("Outcome", className="help-label help-label-outcome"),
                    html.P(tutorial["outcome"], className="help-outcome-text"),
                ],
                className="help-outcome",
            ),
        ]
    else:
        content = [html.H4(title), html.P(text)]
    return html.Details(
        [
            html.Summary([icon("lucide:circle-help", 14), " Help"]),
            html.Div(content, className="help-body tutorial-help"),
        ],
        className="help-panel",
    )


def header(
    title: str,
    actions=None,
    help_text: str | None = None,
    user: dict | None = None,
    pathname: str | None = None,
    agentic: bool = False,
):
    display = display_user(user)
    crumbs = breadcrumb(pathname) if pathname else None
    return html.Header(
        [
            html.Div(
                [
                    crumbs,
                    html.H1(title, className="page-title"),
                    html.Div(
                        [
                            module_help(title, help_text) if help_text else None,
                            agentic_button() if agentic else None,
                        ],
                        className="header-assist-row",
                    ),
                ],
                className="header-title-group",
            ),
            html.Div(
                [
                    *(actions or []),
                    html.Button([icon("lucide:moon", 12), html.Span("Theme")], id="theme-toggle", className="btn-secondary", title="Toggle light or dark theme"),
                    html.Button([icon("lucide:globe", 12), html.Span("English")], className="btn-secondary"),
                    dcc.Link(icon("lucide:bell", 16), href="/notifications", className="icon-button"),
                    html.Div(
                        [
                            html.Div(display["initials"], className="user-avatar super-admin-avatar" if user and user.get("role") == "SUPER_ADMIN" else "user-avatar"),
                            html.Div(
                                [
                                    html.Div(display["name"], style={"fontSize": "12px", "fontWeight": 620}),
                                    html.Div(display["company"], style={"fontSize": "10px", "color": "var(--mist-400)"}),
                                ]
                            ),
                        ],
                        className="header-actions",
                        style={"borderLeft": "1px solid var(--mist-200)", "paddingLeft": "10px"},
                    ),
                ],
                className="header-actions",
            ),
        ],
        className="top-header",
    )


def app_shell(page_content, pathname: str = "/dashboard", title: str = "ZCAMS", user: dict | None = None, theme_mode: str = "light"):
    display = display_user(user)
    super_admin_banner = (
        html.Div(
            [
                html.Div(
                    [
                        icon("lucide:shield-check", 16),
                        html.Strong("Super Admin Console"),
                        html.Span("Platform-wide oversight for CFA approvals, compliance monitoring, audit events, and support escalation."),
                    ],
                    className="super-admin-banner-copy",
                ),
                html.Div(display["email"], className="super-admin-banner-email"),
            ],
            className="super-admin-banner",
        )
        if user and user.get("role") == "SUPER_ADMIN"
        else None
    )
    show_workflow = pathname not in {"/notifications", "/support", "/chat", "/gn83", "/contracts", "/company-profile"}
    return html.Div(
        [
            sidebar(pathname, user),
            html.Main(
                [
                    super_admin_banner,
                    workflow_strip(pathname) if show_workflow else None,
                    page_content,
                ],
                className="main-area",
            ),
        ],
        className=f"app-shell theme-{theme_mode}{' super-admin-shell' if user and user.get('role') == 'SUPER_ADMIN' else ''}",
    )
