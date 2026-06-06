from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update, register_page

from components.icons import icon
from components.layout import public_nav


register_page(__name__, path="/tutorials", name="Tutorial")

THEME_HEAD_GRADIENT = {
    "overview": "linear-gradient(120deg, #06451f 0%, #0b6b34 55%, #1a8f4c 100%)",
    "admin": "linear-gradient(120deg, #1e3a8a 0%, #2563eb 60%, #3b82f6 100%)",
    "zsad": "linear-gradient(120deg, #0f766e 0%, #0d9488 55%, #14b8a6 100%)",
    "invoice": "linear-gradient(120deg, #92400e 0%, #d97706 55%, #f59e0b 100%)",
    "tools": "linear-gradient(120deg, #5b21b6 0%, #7c3aed 55%, #8b5cf6 100%)",
    "roles": "linear-gradient(120deg, #06451f 0%, #1d4ed8 50%, #7c3aed 100%)",
    "summary": "linear-gradient(120deg, #14532d 0%, #15803d 55%, #22c55e 100%)",
}

THEME_BODY_GRADIENT = {
    "overview": "linear-gradient(180deg, #ecfdf3 0%, #fff 72%)",
    "admin": "linear-gradient(180deg, #dbeafe 0%, #fff 72%)",
    "zsad": "linear-gradient(180deg, #ccfbf1 0%, #fff 72%)",
    "invoice": "linear-gradient(180deg, #fef3c7 0%, #fff 72%)",
    "tools": "linear-gradient(180deg, #ede9fe 0%, #fff 72%)",
    "roles": "linear-gradient(180deg, #e2e8f0 0%, #fff 72%)",
    "summary": "linear-gradient(180deg, #dcfce7 0%, #fff 72%)",
}


def _admin_panel(title: str, detail: str, icon_name: str, *, tone: str = "green") -> html.Div:
    return html.Div(
        [
            html.Div(icon(icon_name, 18), className="tutorial-panel-icon"),
            html.Strong(title),
            html.P(detail, className="tutorial-panel-copy"),
        ],
        className=f"tutorial-panel-card tone-{tone}",
    )


def _flow_step(number: int, title: str, location: str, detail: str, *, tone: str = "green") -> html.Div:
    return html.Div(
        [
            html.Span(str(number), className=f"tutorial-step-num tone-{tone}"),
            html.Div(
                [
                    html.Strong(title),
                    html.Span(location, className=f"tutorial-step-loc tone-{tone}"),
                    html.P(detail, className="tutorial-panel-copy"),
                ],
                className="tutorial-step-copy",
            ),
        ],
        className=f"tutorial-flow-step tone-{tone}",
    )


def _flow_grid(*steps: html.Div) -> html.Div:
    items: list = []
    for idx, step in enumerate(steps):
        items.append(step)
        if idx < len(steps) - 1:
            items.append(
                html.Div(icon("lucide:chevron-down", 20), className="tutorial-flow-arrow"),
            )
    return html.Div(items, className="tutorial-flow-timeline")


def _tool_tile(number: str, title: str, detail: str, *, tone: str = "violet") -> html.Div:
    return html.Div(
        [
            html.Span(number, className=f"tutorial-tool-num tone-{tone}"),
            html.Strong(title),
            html.P(detail, className="tutorial-panel-copy"),
        ],
        className=f"tutorial-tool-card tone-{tone}",
    )


def _role_card(role: str, goal: str, actions: str, icon_name: str, *, tone: str = "green") -> html.Div:
    return html.Div(
        [
            html.Div(icon(icon_name, 16), className="tutorial-role-icon"),
            html.Strong(role),
            html.Span(goal, className="tutorial-role-goal"),
            html.P(actions, className="tutorial-panel-copy"),
        ],
        className=f"tutorial-role-card tone-{tone}",
    )


def _build_slides() -> list[dict]:
    return [
    {
        "id": "title",
        "theme": "overview",
        "tag": "Overview",
        "title": "ZCAMS Tutorial",
        "subtitle": "High-level Z-SAD and Invoice generation — viewed from the Company Admin command centre.",
        "body": [
            html.Div(
                [
                    html.Img(src="/assets/zcams-logo.png", className="tutorial-hero-logo", alt="ZCAMS"),
                    html.Div(
                        [
                            html.P(
                                "This presentation explains how ZCAMS moves a Bill of Lading into an active Z-SAD "
                                "and GN 83 invoice, and how the Company Admin page monitors and supports that journey.",
                                className="tutorial-lead",
                            ),
                            html.Div(
                                [
                                    html.Span("System", className="tutorial-chip tone-blue"),
                                    html.Span("Company Admin scope", className="tutorial-chip tone-violet"),
                                    html.Span("Z-SAD + Invoice", className="tutorial-chip tone-green"),
                                ],
                                className="tutorial-chip-row",
                            ),
                        ],
                    ),
                ],
                className="tutorial-title-hero",
            ),
        ],
    },
    {
        "id": "admin-hub",
        "theme": "admin",
        "tag": "Company Admin",
        "title": "Company Administration Command Centre",
        "subtitle": "The /admin page is the CFA tenant oversight console — not the place where Z-SADs are issued.",
        "body": [
            html.Div(
                [
                    _admin_panel("Dashboard Summary", "Compliance, users, pending BLs, invoices, releases, tickets, contracts, documents.", "lucide:layout-dashboard", tone="green"),
                    _admin_panel("Access Control", "Create, update, suspend, activate, or delete Declarant users for this CFA.", "lucide:users-round", tone="blue"),
                    _admin_panel("Operational Oversight", "Shipment workflow table: BL → Z-SAD → invoice → payment → release.", "lucide:workflow", tone="teal"),
                    _admin_panel("Compliance & Alerts", "Profile readiness, contracts, notifications, support tickets, audit events.", "lucide:shield-check", tone="amber"),
                    _admin_panel("Support Tools", "Shipment, payment, user, document, and GN 83 lookup utilities.", "lucide:life-buoy", tone="violet"),
                ],
                className="tutorial-admin-grid",
            ),
            html.P(
                "Declarants execute BL capture and invoicing. Company Admin watches the tenant pipeline and resolves blockers.",
                className="tutorial-note",
            ),
        ],
    },
    {
        "id": "zsad-flow",
        "theme": "zsad",
        "tag": "Z-SAD",
        "title": "How a Z-SAD Is Generated",
        "subtitle": "System flow from BL capture to one active Z-SAD per shipment.",
        "body": [
            _flow_grid(
                _flow_step(1, "BL Upload / Capture", "/bls", "Declarant uploads or captures the Bill of Lading and verifies OCR draft values.", tone="teal"),
                _flow_step(2, "Save BL", "/bls", "ZCAMS stores the BL, classifies GN 83 cargo, and auto-reviews the record.", tone="green"),
                _flow_step(3, "Z-SAD Issued", "Reviewed BL", "Z-SAD is issued—a single-use active number is generated and linked to the BL—and the GN 83 invoice is built and downloaded.", tone="blue"),
                _flow_step(4, "Admin Oversight", "/admin", "Operational Oversight table shows BL status, Z-SAD, invoice, and payment columns.", tone="violet"),
            ),
            html.Div(
                [
                    html.Strong("Company Admin sees:"),
                    html.Ul(
                        [
                            html.Li("Pending BLs waiting for Declarant action."),
                            html.Li("Active Z-SAD on each reviewed shipment."),
                            html.Li("Duplicate BL conflicts requiring detach before re-upload."),
                        ],
                        className="tutorial-bullets",
                    ),
                ],
                className="tutorial-callout tone-teal",
            ),
        ],
    },
    {
        "id": "invoice-flow",
        "theme": "invoice",
        "tag": "Invoice",
        "title": "How an Invoice Is Generated",
        "subtitle": "GN 83 Full Settlement billing after the Z-SAD is active.",
        "body": [
            _flow_grid(
                _flow_step(1, "Reviewed BL Ready", "/reviewed-bl", "Active reviewed BL carries the live Z-SAD and consignee details.", tone="amber"),
                _flow_step(2, "Request Full Settlement", "Invoice modal", "Declarant opens Full Settlement, confirms beneficiary contact details.", tone="gold"),
                _flow_step(3, "GN 83 Calculation", "Server", "ZCAMS applies minimum fee, admin fee, VAT, and total from the GN 83 schedule.", tone="green"),
                _flow_step(4, "Invoice PDF + CapitalPay", "/invoices", "Invoice record, bank invoice ref, PDF notice, and checkout link are created.", tone="blue"),
                _flow_step(5, "Payment & Release", "/checkout", "Payer settles via CapitalPay; cargo release follows settlement rules.", tone="teal"),
            ),
            html.Div(
                [
                    html.Strong("Company Admin tools for billing support:"),
                    html.Ul(
                        [
                            html.Li("Operational Oversight — invoice and payment status per BL."),
                            html.Li("Payment & CapitalPay Resolver — lookup by invoice or checkout ref."),
                            html.Li("GN 83 Fee Explainer — recalculate fee from stored BL category."),
                        ],
                        className="tutorial-bullets",
                    ),
                ],
                className="tutorial-callout tone-amber",
            ),
        ],
    },
    {
        "id": "admin-tools",
        "theme": "tools",
        "tag": "Support Tools",
        "title": "Company Admin Support Tools",
        "subtitle": "Five lookup utilities on /admin#tools for live customer-service calls.",
        "body": [
            html.Div(
                [
                    _tool_tile("1", "Shipment & Clearance Tracker", "BL → Z-SAD → invoice → payment → release", tone="teal"),
                    _tool_tile("2", "Payment & CapitalPay Resolver", "Checkout link, invoice status, GN 83 total", tone="amber"),
                    _tool_tile("3", "User Access & Login Diagnostic", "Account status, role, recent sign-in attempts", tone="blue"),
                    _tool_tile("4", "Document & Certificate Check", "Onboarding completeness for the CFA", tone="green"),
                    _tool_tile("5", "GN 83 Fee Explainer", "Minimum fee from stored BL cargo category", tone="violet"),
                ],
                className="tutorial-tool-grid",
            ),
            html.P(
                "These tools do not replace Declarant workflow actions. They help Company Admin explain where a shipment is stuck.",
                className="tutorial-note",
            ),
        ],
    },
    {
        "id": "roles",
        "theme": "roles",
        "tag": "BTW — Roles",
        "title": "Roles, Goals & Responsibilities",
        "subtitle": "Who does what in ZCAMS — high-level system boundaries.",
        "body": [
            html.Div(
                [
                    _role_card("Super Admin", "Platform control", "Onboard CFAs, manage all five roles, audit platform-wide activity.", "lucide:shield", tone="violet"),
                    _role_card("Admin Support", "Cross-tenant support", "Resolve Company Admin and Declarant access issues; no platform control.", "lucide:life-buoy", tone="blue"),
                    _role_card("Operations", "Settlement operations", "Review payment-backed invoice runs and export settlement reports.", "lucide:landmark", tone="amber"),
                    _role_card("Company Admin", "Tenant command centre", "Manage Declarants, monitor BL/Z-SAD/invoice health, run support lookups.", "lucide:settings", tone="green"),
                    _role_card("Declarant", "Shipment execution", "Capture BLs, issue Z-SADs, request invoices, share checkout links.", "lucide:file-up", tone="teal"),
                ],
                className="tutorial-role-grid",
            ),
        ],
    },
    {
        "id": "summary",
        "theme": "summary",
        "tag": "Summary",
        "title": "Key Takeaways",
        "subtitle": "Z-SAD and invoice generation in one view.",
        "body": [
            html.Ol(
                [
                    html.Li("Z-SAD is created when a BL is saved and reviewed — one active Z-SAD per BL journey."),
                    html.Li("Invoice is requested from Reviewed BL using Full Settlement after the Z-SAD is active."),
                    html.Li("Company Admin does not issue Z-SADs or invoices — they monitor and support Declarants."),
                    html.Li("Use Operational Oversight and Support Tools on /admin to trace any blocked shipment."),
                    html.Li("Platform, support, and settlement roles stay outside the CFA tenant workflow."),
                ],
                className="tutorial-summary-list",
            ),
            html.Div(
                [
                    html.Span("BLs", className="tutorial-chip tone-blue"),
                    html.Span("→", className="tutorial-arrow"),
                    html.Span("Z-SAD", className="tutorial-chip tone-teal"),
                    html.Span("→", className="tutorial-arrow"),
                    html.Span("Invoice", className="tutorial-chip tone-amber"),
                    html.Span("→", className="tutorial-arrow"),
                    html.Span("CapitalPay", className="tutorial-chip tone-violet"),
                    html.Span("→", className="tutorial-arrow"),
                    html.Span("Release", className="tutorial-chip tone-green"),
                ],
                className="tutorial-chip-row center",
            ),
        ],
    },
    ]


SLIDES = _build_slides()


def _slide_view(index: int) -> html.Div:
    slide = SLIDES[index]
    theme = slide.get("theme", "overview")
    return html.Div(
        [
            html.Div(
                [
                    html.Span(slide["tag"], className="tutorial-slide-tag"),
                    html.H2(slide["title"], className="tutorial-slide-title"),
                    html.P(slide["subtitle"], className="tutorial-slide-subtitle"),
                ],
                className="tutorial-slide-head",
                style={"background": THEME_HEAD_GRADIENT.get(theme, THEME_HEAD_GRADIENT["overview"])},
            ),
            html.Div(
                slide["body"],
                className="tutorial-slide-body",
                style={"background": THEME_BODY_GRADIENT.get(theme, THEME_BODY_GRADIENT["overview"])},
            ),
        ],
        className=f"tutorial-slide-frame theme-{theme}",
    )


def _progress_dots(active: int) -> html.Div:
    return html.Div(
        [
            html.Button(
                className=f"tutorial-dot{' is-active' if idx == active else ''}",
                id={"type": "tutorial-dot", "index": idx},
                title=SLIDES[idx]["title"],
                type="button",
            )
            for idx in range(len(SLIDES))
        ],
        className="tutorial-dots",
    )


def layout(**_kwargs):
    return html.Div(
        [
            dcc.Store(id="tutorial-slide-index", data=0),
            public_nav(active="basics"),
            html.Main(
                [
                    html.Div(
                        [
                            html.Div(id="tutorial-slide-stage", children=_slide_view(0)),
                            html.Div(
                                [
                                    html.Button(
                                        [icon("lucide:chevron-left", 16), "Previous"],
                                        id="tutorial-prev",
                                        className="btn-secondary",
                                        type="button",
                                    ),
                                    html.Div(id="tutorial-progress", children=_progress_dots(0)),
                                    html.Span(id="tutorial-counter", children=f"1 / {len(SLIDES)}", className="tutorial-counter"),
                                    html.Button(
                                        ["Next", icon("lucide:chevron-right", 16)],
                                        id="tutorial-next",
                                        className="btn-primary",
                                        type="button",
                                    ),
                                ],
                                className="tutorial-nav-bar",
                            ),
                        ],
                        className="tutorial-deck-card",
                    ),
                ],
                className="tutorial-deck-page public-tutorial-main",
            ),
        ],
        className="public-page public-tutorial-page",
    )


def _slide_outputs(index: int):
    total = len(SLIDES)
    index = max(0, min(index, total - 1))
    return _slide_view(index), _progress_dots(index), f"{index + 1} / {total}", index


@callback(
    Output("tutorial-slide-stage", "children"),
    Output("tutorial-progress", "children"),
    Output("tutorial-counter", "children"),
    Output("tutorial-slide-index", "data"),
    Input("tutorial-prev", "n_clicks"),
    Input("tutorial-next", "n_clicks"),
    Input({"type": "tutorial-dot", "index": ALL}, "n_clicks"),
    State("tutorial-slide-index", "data"),
    prevent_initial_call=True,
)
def navigate_tutorial(prev_clicks, next_clicks, dot_clicks, current_index):
    current = int(current_index or 0)
    trigger = ctx.triggered_id
    if trigger == "tutorial-prev":
        return _slide_outputs(current - 1)
    if trigger == "tutorial-next":
        return _slide_outputs(current + 1)
    if isinstance(trigger, dict) and trigger.get("type") == "tutorial-dot":
        return _slide_outputs(int(trigger.get("index", 0)))
    return (no_update,) * 4
