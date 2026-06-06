import dash_ag_grid as dag
from dash import Input, Output, State, callback, ctx, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate

from components.icons import icon
from components.layout import header, section_label
from services import auth, repository


register_page(__name__, path="/admin", name="Company Admin")


def _tool_card(title: str, description: str, tool_id: str, placeholder: str):
    return html.Div(
        [
            html.H3(title),
            html.P(description, className="muted"),
            dcc.Input(id=f"admin-tool-{tool_id}-query", placeholder=placeholder, className="form-control"),
            html.Button("Run lookup", id=f"admin-tool-{tool_id}-run", className="btn-secondary", type="button"),
            html.Div(id=f"admin-tool-{tool_id}-result", className="stack compact"),
        ],
        className="card section-card stack admin-tool-card",
    )


def _admin_grid(grid_id: str, columns: list[dict], row_data: list[dict] | None = None, height: int = 320):
    select_col = {
        "headerName": "",
        "field": "_select",
        "checkboxSelection": True,
        "headerCheckboxSelection": True,
        "width": 52,
        "pinned": "left",
        "sortable": False,
        "filter": False,
    }
    return dag.AgGrid(
        id=grid_id,
        className="ag-theme-alpine zcams-ag-grid admin-ag-grid",
        columnDefs=[select_col, *columns],
        rowData=row_data or [],
        defaultColDef={
            "sortable": True,
            "filter": True,
            "resizable": True,
            "wrapText": True,
            "autoHeight": True,
        },
        dashGridOptions={
            "rowSelection": "multiple",
            "rowMultiSelectWithClick": True,
            "suppressRowClickSelection": False,
            "animateRows": True,
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
        },
        style={"height": f"{height}px", "width": "100%"},
    )


def _section_title(title: str, subtitle: str, icon_name: str):
    return html.Div(
        [
            html.Div(icon(icon_name, 22), className="admin-section-icon"),
            html.Div([html.H2(title), html.P(subtitle, className="muted section-lead")]),
        ],
        className="admin-section-title",
    )


def _role_options():
    return [
        {"label": "Declarant / Agent", "value": auth.ROLE_DECLARANT},
    ]


def _company_id_for_admin(user: dict | None) -> str:
    _require_company_admin(user)
    return (user or {}).get("company_id") or repository.DEMO_COMPANY_ID


def _notice(message: str, kind: str = "success"):
    return html.Div(message, className=f"notice {kind}")


def _mail_progress(label: str = "Waiting for resend action.", percent: int = 0, state: str = "idle"):
    visible = state != "idle"
    percent = max(0, min(100, int(percent)))
    return html.Div(
        [
            html.Div([html.Span(label), html.Span(f"{percent}%")], className="mail-progress-label"),
            html.Div(html.Div(style={"width": f"{percent}%"}, className="mail-progress-fill"), className="mail-progress-track"),
        ],
        className=f"mail-progress {state}{' is-visible' if visible else ''}",
    )


def _metric_card(title: str, value, icon_name: str, tone: str = "green", detail: str | None = None):
    return html.Div(
        [
            html.Div(icon(icon_name, 18), className=f"admin-metric-icon {tone}"),
            html.Div(
                [
                    html.Span(title, className="admin-metric-label"),
                    html.Strong(str(value), className="admin-metric-value"),
                    html.Small(detail or "", className="muted"),
                ],
                className="stack compact",
            ),
        ],
        className="admin-metric-card",
    )


def _admin_search(search_id: str, placeholder: str):
    return html.Div(
        [
            icon("lucide:search", 15),
            dcc.Input(id=search_id, placeholder=placeholder, className="form-control admin-search-input", debounce=True),
        ],
        className="admin-search-bar",
    )


def _grid_block(title: str, tooltip: str, grid):
    return html.Div(
        [
            html.Div(
                [
                    html.H3(title),
                    html.Span("?", className="admin-help-dot", title=tooltip),
                ],
                className="admin-grid-heading",
            ),
            grid,
        ],
        className="admin-grid-block",
    )


def _matches_search(row: dict, search: str | None) -> bool:
    term = (search or "").strip().lower()
    if not term:
        return True
    return term in " ".join(str(value or "") for value in row.values()).lower()


def _admin_user_rows(company_id: str) -> list[dict]:
    rows = []
    for user in repository.list_company_users(company_id):
        rows.append(
            {
                **user,
                "name": f"{user.get('first_name') or ''} {user.get('last_name') or ''}".strip(),
                "role_label": auth.role_label(user.get("role")),
            }
        )
    return rows


def _admin_attention_rows(notifications: list[dict], tickets: list[dict], audits: list[dict]) -> list[dict]:
    rows = []
    for item in notifications:
        is_read = bool(item.get("is_read"))
        rows.append(
            {
                "type": "Notification",
                "subject": item.get("message") or "-",
                "recommended_action": "Review notification" if not is_read else "No action needed",
                "status": "Unread" if not is_read else "Read",
                "owner": "Company Admin",
                "created_at": item.get("created_at") or "-",
            }
        )
    for ticket in tickets:
        status = ticket.get("status") or "Open"
        rows.append(
            {
                "type": "Support Ticket",
                "subject": ticket.get("subject") or "-",
                "recommended_action": "Respond or resolve ticket" if status.upper() != "RESOLVED" else "Closed",
                "status": f"{status} | {ticket.get('priority') or 'Normal'}",
                "owner": ticket.get("created_by_email") or "-",
                "created_at": ticket.get("created_at") or "-",
            }
        )
    for audit in audits:
        rows.append(
            {
                "type": "Audit Event",
                "subject": f"{audit.get('entity_type') or 'Record'} | {audit.get('details') or '-'}",
                "recommended_action": "Audit trail only",
                "status": audit.get("action") or "-",
                "owner": audit.get("actor_email") or "-",
                "created_at": audit.get("created_at") or "-",
            }
        )
    return sorted(rows, key=lambda row: row.get("created_at") or "", reverse=True)


def _selected_user_id(selected_rows: list[dict] | None) -> str:
    if not selected_rows:
        raise ValueError("Select one user from the table first.")
    return selected_rows[0].get("id")


def layout(**_kwargs):
    return html.Div(
        [
            header(
                "Company Administration",
                help_text="Tenant command centre: compliance, access control, operations, contracts, alerts, and support tools.",
                pathname="/admin",
            ),
            dcc.Store(id="admin-dashboard-refresh", data=0),
            html.Div(
                [
                    html.Div(id="admin-dashboard-summary", className="admin-dashboard-summary"),
                    html.Div(
                        [
                            _section_title(
                                "Access Control",
                                "Create users, update roles, and suspend or delete tenant accounts with company-admin safeguards.",
                                "lucide:users-round",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            dcc.Input(id="admin-user-first-name", placeholder="First name", className="form-control"),
                                            dcc.Input(id="admin-user-last-name", placeholder="Last name", className="form-control"),
                                            dcc.Input(id="admin-user-email", placeholder="Email", className="form-control"),
                                            dcc.Input(id="admin-user-phone", placeholder="Phone", className="form-control"),
                                            dcc.Input(id="admin-user-whatsapp", placeholder="WhatsApp", className="form-control"),
                                            dcc.Dropdown(
                                                id="admin-user-role",
                                                options=_role_options(),
                                                value=auth.ROLE_DECLARANT,
                                                clearable=False,
                                                className="admin-dropdown",
                                            ),
                                        ],
                                        className="admin-form-grid",
                                    ),
                                    html.Div(
                                        [
                                            html.Button([icon("lucide:user-plus", 14), "Create"], id="admin-user-create", className="btn-primary", type="button"),
                                            html.Button([icon("lucide:save", 14), "Update Selected"], id="admin-user-update", className="btn-secondary", type="button"),
                                            html.Button([icon("lucide:user-check", 14), "Activate"], id="admin-user-activate", className="btn-secondary", type="button"),
                                            html.Button([icon("lucide:user-x", 14), "Suspend"], id="admin-user-suspend", className="btn-warning", type="button"),
                                            html.Button([icon("lucide:mail-check", 14), "Resend Email"], id="admin-user-resend-email", className="btn-secondary", type="button"),
                                            html.Button([icon("lucide:trash-2", 14), "Delete"], id="admin-user-delete", className="btn-danger", type="button"),
                                            html.Button([icon("lucide:refresh-cw", 14), "Refresh"], id="admin-user-refresh", className="btn-secondary", type="button"),
                                        ],
                                        className="row-actions admin-actions",
                                    ),
                                    html.Div(id="admin-user-action-message"),
                                    html.Div(id="admin-user-resend-progress-live", children=_mail_progress()),
                                    html.Div(id="admin-user-resend-progress", children=_mail_progress()),
                                    section_label(
                                        "Declarant User Register",
                                        "Create, select, update, activate, suspend, or delete Declarant accounts for this CFA only.",
                                        "lucide:users-round",
                                    ),
                                    _admin_search("admin-user-search", "Search users by name, email, role, or status..."),
                                    _admin_grid(
                                        "admin-users-grid",
                                        [
                                            {"headerName": "Name", "field": "name", "minWidth": 180},
                                            {"headerName": "Email", "field": "email", "minWidth": 220},
                                            {"headerName": "Role", "field": "role_label", "minWidth": 150},
                                            {"headerName": "Status", "field": "status", "minWidth": 120},
                                            {"headerName": "Created", "field": "created_at", "minWidth": 170},
                                        ],
                                    ),
                                ],
                                className="stack",
                            ),
                        ],
                        className="card section-card stack admin-command-section",
                        id="access-control",
                    ),
                    html.Div(
                        [
                            _section_title(
                                "Operational Oversight",
                                "Company-scoped BL, Z-SAD, invoice, payment, and release health in one table.",
                                "lucide:workflow",
                            ),
                            section_label(
                                "Shipment Workflow Table",
                                "Search company BLs and follow each shipment through review, Z-SAD, invoice, payment, and release status.",
                                "lucide:table-properties",
                            ),
                            _admin_search("admin-operational-search", "Search BL, consignee, Z-SAD, invoice, status, or payment..."),
                            html.Div(id="admin-operational-overview"),
                        ],
                        className="card section-card stack admin-command-section",
                    ),
                    html.Div(
                        [
                            _section_title(
                                "Compliance, Contracts & Alerts",
                                "Profile readiness, documents, contract signature state, notifications, and open support tickets.",
                                "lucide:shield-check",
                            ),
                            section_label(
                                "Attention & Activity Feed",
                                "Review company readiness, documents, contracts, notifications, support tickets, and audit activity in one place.",
                                "lucide:list-checks",
                            ),
                            html.Div(id="admin-compliance-overview"),
                        ],
                        className="card section-card stack admin-command-section",
                    ),
                    html.Div(
                        [
                            _section_title(
                                "Customer Service Support Tools",
                                "Use these lookups during support calls. Enter one identifier and get an actionable answer.",
                                "lucide:life-buoy",
                            ),
                            section_label(
                                "Guided Lookup Tools",
                                "Use these support utilities during calls to resolve shipment, payment, user, document, and GN 83 questions.",
                                "lucide:search-check",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            _tool_card(
                                                "1. Shipment & Clearance Tracker",
                                                "Where is the cargo? BL to Z-SAD to invoice to payment to release.",
                                                "shipment",
                                                "BL number, Z-SAD, or invoice number",
                                            ),
                                            _tool_card(
                                                "2. Payment & CapitalPay Resolver",
                                                "Checkout link, invoice status, and GN 83 total.",
                                                "payment",
                                                "Invoice number e.g. INV-20260527...",
                                            ),
                                        ],
                                        className="admin-tools-row admin-tools-row-two",
                                    ),
                                    html.Div(
                                        [
                                            _tool_card(
                                                "3. User Access & Login Diagnostic",
                                                "Account status, role, and recent sign-in attempts.",
                                                "user",
                                                "Email or username",
                                            ),
                                            _tool_card(
                                                "4. Document & Certificate Check",
                                                "Onboarding completeness for the company.",
                                                "documents",
                                                "Company name or leave blank for your CFA",
                                            ),
                                            _tool_card(
                                                "5. GN 83 Fee Explainer",
                                                "Recalculate minimum fee from stored BL cargo category.",
                                                "fee",
                                                "BL number",
                                            ),
                                        ],
                                        className="admin-tools-row admin-tools-row-three",
                                    ),
                                ],
                                className="admin-tools-grid",
                            ),
                        ],
                        className="stack",
                        id="tools",
                    ),
                ],
                className="page-content stack",
            ),
        ]
    )


def _require_company_admin(user: dict | None):
    role = auth.normalize_role((user or {}).get("role"))
    if role not in {auth.ROLE_COMPANY_ADMIN, auth.ROLE_SUPER_ADMIN}:
        raise PermissionError("Company Admin access required.")


@callback(
    Output("admin-dashboard-summary", "children"),
    Input("auth-user", "data"),
    Input("admin-dashboard-refresh", "data"),
)
def render_admin_dashboard_summary(user, _refresh):
    company_id = _company_id_for_admin(user)
    summary = repository.admin_dashboard_summary(company_id)
    missing = summary.get("missing_fields") or []
    return html.Div(
        [
            html.Div(
                [
                    html.H2(summary.get("company_name")),
                    html.P(
                        f"Tenant status: {summary.get('company_status')} | Banking ready: {'Yes' if summary.get('banking_ready') else 'No'}",
                        className="muted",
                    ),
                ],
                className="admin-hero-copy",
            ),
            html.Div(
                [
                    _metric_card("Compliance", f"{summary.get('compliance_score')}%", "lucide:shield-check", "green", f"{len(missing)} missing fields"),
                    _metric_card("Active Users", summary.get("active_users"), "lucide:user-check", "blue", f"{summary.get('suspended_users')} suspended"),
                    _metric_card("Pending BLs", summary.get("bls_pending"), "lucide:file-clock", "amber", "Awaiting review"),
                    _metric_card("Outstanding Invoices", summary.get("outstanding_invoices"), "lucide:receipt", "red", "Not settled"),
                    _metric_card("Pending Releases", summary.get("release_pending"), "lucide:package-check", "purple", "After payment"),
                    _metric_card("Open Tickets", summary.get("open_tickets"), "lucide:life-buoy", "amber", "Support workload"),
                    _metric_card("Contracts", summary.get("signed_contracts"), "lucide:file-signature", "green", f"{summary.get('draft_contracts')} draft"),
                    _metric_card("Documents", summary.get("certificates"), "lucide:folder-check", "blue", "Certificates on file"),
                ],
                className="admin-metrics-grid",
            ),
        ],
        className="admin-hero card section-card",
    )


@callback(
    Output("admin-users-grid", "rowData"),
    Input("auth-user", "data"),
    Input("admin-dashboard-refresh", "data"),
    Input("admin-user-refresh", "n_clicks"),
    Input("admin-user-search", "value"),
)
def render_admin_access_control(user, _refresh, _clicks, search):
    company_id = _company_id_for_admin(user)
    return [row for row in _admin_user_rows(company_id) if _matches_search(row, search)]


@callback(
    Output("admin-user-first-name", "value"),
    Output("admin-user-last-name", "value"),
    Output("admin-user-email", "value"),
    Output("admin-user-phone", "value"),
    Output("admin-user-whatsapp", "value"),
    Output("admin-user-role", "value"),
    Input("admin-users-grid", "selectedRows"),
    prevent_initial_call=True,
)
def load_selected_admin_user(selected_rows):
    if not selected_rows:
        raise PreventUpdate
    selected = selected_rows[0]
    return (
        selected.get("first_name") or "",
        selected.get("last_name") or "",
        selected.get("email") or "",
        selected.get("phone") or "",
        selected.get("whatsapp") or "",
        selected.get("role") or auth.ROLE_DECLARANT,
    )


@callback(
    Output("admin-user-action-message", "children", allow_duplicate=True),
    Output("admin-user-resend-progress", "children"),
    Output("admin-dashboard-refresh", "data", allow_duplicate=True),
    Input("admin-user-create", "n_clicks"),
    Input("admin-user-update", "n_clicks"),
    State("admin-users-grid", "selectedRows"),
    State("admin-user-first-name", "value"),
    State("admin-user-last-name", "value"),
    State("admin-user-email", "value"),
    State("admin-user-phone", "value"),
    State("admin-user-whatsapp", "value"),
    State("admin-user-role", "value"),
    State("auth-user", "data"),
    State("admin-dashboard-refresh", "data"),
    prevent_initial_call=True,
    running=[
        (
            Output("admin-user-resend-progress-live", "children"),
            _mail_progress("Sending login credentials. Please wait...", 68, "sending"),
            _mail_progress(),
        )
    ],
)
def admin_user_create_or_update(_create, _update, selected_rows, first, last, email, phone, whatsapp, role, user, refresh):
    try:
        company_id = _company_id_for_admin(user)
        action = ctx.triggered_id
        if action == "admin-user-create":
            created = repository.create_company_user(company_id, first, last, email, phone or "", whatsapp or "", role)
            if created.get("email_result", {}).get("sent"):
                message = f"Created {created.get('email')}. Credentials were emailed and first-login password setup is required."
            else:
                message = f"Created {created.get('email')}. Email was not confirmed; temporary password: {created.get('temp_password')}"
            return _notice(message), (refresh or 0) + 1
        if action == "admin-user-update":
            user_id = _selected_user_id(selected_rows)
            updated = repository.update_company_user(user_id, company_id, first, last, email, phone or "", whatsapp or "", role)
            return _notice(f"Updated {updated.get('email')}."), (refresh or 0) + 1
    except Exception as exc:  # noqa: BLE001
        return _notice(str(exc), "error"), no_update
    raise PreventUpdate


@callback(
    Output("admin-user-action-message", "children", allow_duplicate=True),
    Output("admin-dashboard-refresh", "data", allow_duplicate=True),
    Input("admin-user-activate", "n_clicks"),
    Input("admin-user-suspend", "n_clicks"),
    Input("admin-user-resend-email", "n_clicks"),
    Input("admin-user-delete", "n_clicks"),
    State("admin-users-grid", "selectedRows"),
    State("auth-user", "data"),
    State("admin-dashboard-refresh", "data"),
    prevent_initial_call=True,
)
def admin_user_status_action(_activate, _suspend, _resend, _delete, selected_rows, user, refresh):
    try:
        company_id = _company_id_for_admin(user)
        user_id = _selected_user_id(selected_rows)
        action = ctx.triggered_id
        if action == "admin-user-delete":
            repository.delete_company_user(user_id, company_id)
            return _notice("Selected user deleted."), _mail_progress(), (refresh or 0) + 1
        if action == "admin-user-resend-email":
            target_ids = [row.get("id") for row in (selected_rows or []) if row.get("id")] or [user_id]
            sent = []
            failed = []
            for target_id in target_ids:
                existing = repository.get_company_user(target_id, company_id)
                if auth.normalize_role((existing or {}).get("role")) != auth.ROLE_DECLARANT:
                    raise ValueError("Company Admin can only resend credentials for Declarant users.")
                delivery = repository.resend_user_credentials(
                    target_id,
                    source="company-admin-resend",
                    actor_role=auth.ROLE_COMPANY_ADMIN,
                )
                email_result = delivery.get("email_result") or {}
                target = (delivery.get("user") or {}).get("email")
                if email_result.get("sent"):
                    sent.append(target or target_id)
                else:
                    failed.append(f"{target or target_id}: temporary password {delivery.get('temp_password')}")
            if failed:
                return (
                    _notice(f"Credentials resent to {len(sent)} user(s). Some emails were not confirmed: {'; '.join(failed)}", "error"),
                    _mail_progress(f"Resend completed with {len(failed)} email issue(s).", 100, "error"),
                    (refresh or 0) + 1,
                )
            return (
                _notice(f"Credentials resent to {len(sent)} user(s). Each user must set a new password on first login."),
                _mail_progress(f"Mail sent to {len(sent)} user(s).", 100, "success"),
                (refresh or 0) + 1,
            )
        status = "SUSPENDED" if action == "admin-user-suspend" else "ACTIVE"
        updated = repository.set_company_user_status(user_id, company_id, status)
        return _notice(f"{updated.get('email')} is now {updated.get('status')}."), _mail_progress(), (refresh or 0) + 1
    except Exception as exc:  # noqa: BLE001
        return _notice(str(exc), "error"), _mail_progress("Resend failed before mail could be sent.", 100, "error"), no_update


@callback(
    Output("admin-operational-overview", "children"),
    Input("auth-user", "data"),
    Input("admin-dashboard-refresh", "data"),
    Input("admin-operational-search", "value"),
)
def render_admin_operational_oversight(user, _refresh, search):
    company_id = _company_id_for_admin(user)
    workflow = [row for row in repository.admin_workflow_rows(company_id) if _matches_search(row, search)]
    return html.Div(
        [
            _admin_grid(
                "admin-workflow-grid",
                [
                    {"headerName": "BL Number", "field": "bl_number", "minWidth": 160},
                    {"headerName": "Consignee", "field": "consignee_name", "minWidth": 190},
                    {"headerName": "BL Status", "field": "bl_status", "minWidth": 150},
                    {"headerName": "Reviewed Status", "field": "reviewed_status", "minWidth": 170},
                    {"headerName": "Z-SAD", "field": "z_sad_number", "minWidth": 190},
                    {"headerName": "Invoice", "field": "invoice_number", "minWidth": 180},
                    {"headerName": "Invoice Status", "field": "invoice_status", "minWidth": 160},
                    {"headerName": "Payment", "field": "payment_status", "minWidth": 140},
                    {"headerName": "Total", "field": "total", "minWidth": 120},
                ],
                workflow,
                height=360,
            )
        ],
        className="stack",
    )


@callback(
    Output("admin-compliance-overview", "children"),
    Input("auth-user", "data"),
    Input("admin-dashboard-refresh", "data"),
)
def render_admin_contracts_notifications_support(user, _refresh):
    company_id = _company_id_for_admin(user)
    summary = repository.admin_dashboard_summary(company_id)
    contracts = repository.admin_contract_rows(company_id)
    notifications = repository.list_notifications(limit=10, company_id=company_id)
    tickets = repository.list_support_tickets(company_id=company_id)
    audits = repository.admin_recent_audit_rows(company_id)
    attention_rows = _admin_attention_rows(notifications, tickets, audits)
    missing = summary.get("missing_fields") or []
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Company Profile & Banking"),
                            html.P("Shows whether the CFA profile and bank details are complete enough for operations.", className="muted section-label-copy"),
                            html.P(f"Compliance score: {summary.get('compliance_score')}%", className="admin-score"),
                            html.P(f"Missing: {', '.join(missing) if missing else 'None'}", className="muted"),
                            html.Div(
                                [
                                    dcc.Link([icon("lucide:building-2", 14), "Edit profile"], href="/company-profile", className="btn-secondary"),
                                    dcc.Link([icon("lucide:file-badge", 14), "Documents"], href="/company-profile#documents", className="btn-secondary"),
                                ],
                                className="row-actions",
                            ),
                        ],
                        className="admin-mini-card",
                    ),
                    html.Div(
                        [
                            html.H3("Team Overview"),
                            html.P("Summarizes company-scoped users and highlights suspended accounts that may need action.", className="muted section-label-copy"),
                            html.P(f"Company Admins: {summary.get('company_admins')}", className="muted"),
                            html.P(f"Declarants: {summary.get('declarants')}", className="muted"),
                            html.P(f"Suspended users: {summary.get('suspended_users')}", className="muted"),
                        ],
                        className="admin-mini-card",
                    ),
                    html.Div(
                        [
                            html.H3("Notifications & Support"),
                            html.P("Highlights unread system events and open tickets that may require company follow-up.", className="muted section-label-copy"),
                            html.P(f"Unread notifications: {summary.get('notifications_unread')}", className="muted"),
                            html.P(f"Open support tickets: {summary.get('open_tickets')}", className="muted"),
                            html.Div(
                                [
                                    dcc.Link([icon("lucide:bell", 14), "Notifications"], href="/notifications", className="btn-secondary"),
                                    dcc.Link([icon("lucide:life-buoy", 14), "Support"], href="/support", className="btn-secondary"),
                                ],
                                className="row-actions",
                            ),
                        ],
                        className="admin-mini-card",
                    ),
                ],
                className="admin-mini-grid",
            ),
            _grid_block(
                "Contracts Register",
                "Importer contract records only: draft/signed state, importer email, creation date, and signature date.",
                _admin_grid(
                    "admin-contracts-grid",
                    [
                        {"headerName": "Contract No.", "field": "contract_no", "minWidth": 150},
                        {"headerName": "Importer", "field": "importer_name", "minWidth": 180},
                        {"headerName": "Importer Email", "field": "importer_email", "minWidth": 220},
                        {"headerName": "Contract Status", "field": "status", "minWidth": 150},
                        {"headerName": "Created", "field": "created_at", "minWidth": 170},
                        {"headerName": "Signed", "field": "signed_at", "minWidth": 170},
                    ],
                    contracts,
                    height=260,
                ),
            ),
            _grid_block(
                "Attention & Activity Feed",
                "Merged view of notifications, support tickets, and immutable audit events. Use Recommended Action to know what needs follow-up.",
                _admin_grid(
                    "admin-attention-grid",
                    [
                        {"headerName": "Type", "field": "type", "minWidth": 150, "tooltipField": "type"},
                        {"headerName": "Subject / Event", "field": "subject", "minWidth": 360, "flex": 1, "tooltipField": "subject"},
                        {"headerName": "Recommended Action", "field": "recommended_action", "minWidth": 220, "tooltipField": "recommended_action"},
                        {"headerName": "Status / Priority", "field": "status", "minWidth": 180},
                        {"headerName": "Owner / Actor", "field": "owner", "minWidth": 220},
                        {"headerName": "Created", "field": "created_at", "minWidth": 170},
                    ],
                    attention_rows,
                    height=360,
                ),
            ),
        ],
        className="stack",
    )


@callback(
    Output("admin-tool-shipment-result", "children"),
    Input("admin-tool-shipment-run", "n_clicks"),
    State("admin-tool-shipment-query", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def tool_shipment(_clicks, query, user):
    try:
        _require_company_admin(user)
        result = auth.cs_lookup_shipment(query)
        if result.get("error"):
            return html.Div(result["error"], className="notice error")
        bl = result["bl"]
        if user.get("role") != auth.ROLE_SUPER_ADMIN and bl.get("company_id") != user.get("company_id"):
            return html.Div("That shipment belongs to another CFA.", className="notice error")
        return html.Div(
            [
                html.Strong(bl.get("bl_number")),
                html.P(f"Company: {bl.get('company_name')}", className="muted"),
                html.P(f"BL status: {bl.get('status')} | Reviewed: {bl.get('reviewed_status') or '-'}"),
                html.P(f"Z-SAD: {bl.get('z_sad_number') or '-'} | Invoice: {bl.get('invoice_number') or '-'}"),
                html.P(f"Invoice status: {bl.get('invoice_status') or '-'} | Payment: {bl.get('payment_status') or '-'}"),
            ],
            className="notice success",
        )
    except Exception as exc:  # noqa: BLE001
        return html.Div(str(exc), className="notice error")


@callback(
    Output("admin-tool-payment-result", "children"),
    Input("admin-tool-payment-run", "n_clicks"),
    State("admin-tool-payment-query", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def tool_payment(_clicks, query, user):
    try:
        _require_company_admin(user)
        inv = repository.row(
            """
            SELECT inv.*, bl.company_id, bl.bl_number, c.name AS company_name
            FROM invoices inv
            JOIN reviewed_bls rb ON rb.id = inv.reviewed_bl_id
            JOIN bills_of_lading bl ON bl.id = rb.bl_id
            LEFT JOIN companies c ON c.id = bl.company_id
            WHERE inv.invoice_number = ?
            """,
            ((query or "").strip(),),
        )
        if not inv:
            return html.Div("Invoice not found.", className="notice error")
        if user.get("role") != auth.ROLE_SUPER_ADMIN and inv.get("company_id") != user.get("company_id"):
            return html.Div("That invoice belongs to another CFA.", className="notice error")
        return html.Div(
            [
                html.Strong(inv.get("invoice_number")),
                html.P(f"BL {inv.get('bl_number')} | {inv.get('company_name')}", className="muted"),
                html.P(f"Status: {inv.get('status')} | Total: {repository.money(inv.get('total') or 0)}"),
                html.P(f"CapitalPay URN: {inv.get('capitalpay_urn') or 'Not set'}"),
                html.A("Open checkout", href=inv.get("checkout_url") or "/checkout", target="_blank", className="text-link")
                if inv.get("checkout_url")
                else html.Span("No checkout URL yet.", className="muted"),
            ],
            className="notice success",
        )
    except Exception as exc:  # noqa: BLE001
        return html.Div(str(exc), className="notice error")


@callback(
    Output("admin-tool-user-result", "children"),
    Input("admin-tool-user-run", "n_clicks"),
    State("admin-tool-user-query", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def tool_user(_clicks, query, user):
    try:
        _require_company_admin(user)
        result = auth.cs_lookup_user(query)
        if result.get("error"):
            return html.Div(result["error"], className="notice error")
        u = result["user"]
        if user.get("role") != auth.ROLE_SUPER_ADMIN and u.get("company_id") != user.get("company_id"):
            return html.Div("That user belongs to another CFA.", className="notice error")
        logins = result.get("recent_logins") or []
        return html.Div(
            [
                html.Strong(f"{u.get('first_name')} {u.get('last_name')}"),
                html.P(f"{auth.role_label(u.get('role'))} | {u.get('status')} | {u.get('email')}", className="muted"),
                html.P(f"Company: {u.get('company_name')} ({u.get('company_status')})"),
                html.Ul([html.Li(f"{l.get('created_at')[:19]} - {'OK' if l.get('success') else 'Failed'} - {l.get('ip_address') or '-'}") for l in logins])
                if logins
                else html.P("No recent login events.", className="muted"),
            ],
            className="notice success",
        )
    except Exception as exc:  # noqa: BLE001
        return html.Div(str(exc), className="notice error")


@callback(
    Output("admin-tool-documents-result", "children"),
    Input("admin-tool-documents-run", "n_clicks"),
    State("admin-tool-documents-query", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def tool_documents(_clicks, _query, user):
    try:
        _require_company_admin(user)
        company_id = user.get("company_id") or repository.DEMO_COMPANY_ID
        company = repository.get_company(company_id)
        score = repository.compliance_score(company_id)
        certs = repository.list_certificates(company_id)
        missing = []
        for field, label in [
            ("pacra_number", "PACRA"),
            ("tpin", "TPIN"),
            ("zra_licence", "ZRA licence"),
            ("bank_name", "Bank name"),
            ("account_number", "Account number"),
        ]:
            if not company.get(field):
                missing.append(label)
        return html.Div(
            [
                html.Strong(company.get("name") or company_id),
                html.P(f"Compliance score: {score}% | Certificates on file: {len(certs)}", className="muted"),
                html.P(f"Missing fields: {', '.join(missing) if missing else 'None'}"),
            ],
            className="notice success",
        )
    except Exception as exc:  # noqa: BLE001
        return html.Div(str(exc), className="notice error")


@callback(
    Output("admin-tool-fee-result", "children"),
    Input("admin-tool-fee-run", "n_clicks"),
    State("admin-tool-fee-query", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def tool_fee(_clicks, query, user):
    try:
        _require_company_admin(user)
        bl = repository.row(
            """
            SELECT bl.*, ci.gn83_category, ci.quantity, ci.unit
            FROM bills_of_lading bl
            LEFT JOIN cargo_items ci ON ci.bl_id = bl.id
            WHERE bl.bl_number = ?
            LIMIT 1
            """,
            ((query or "").strip(),),
        )
        if not bl:
            return html.Div("BL not found.", className="notice error")
        if user.get("role") != auth.ROLE_SUPER_ADMIN and bl.get("company_id") != user.get("company_id"):
            return html.Div("That BL belongs to another CFA.", className="notice error")
        from services.gn83 import calculate_invoice, lookup_fee

        category = bl.get("gn83_category") or "LOOSE_LCL"
        std = lookup_fee(
            bl.get("route_type") or "Import",
            bl.get("transport_mode") or "Sea",
            category,
            quantity=1,
            no_containers=int(bl.get("no_containers") or 0),
            gross_weight=float(bl.get("gross_weight") or 0),
        )
        calc = calculate_invoice(std, "FULL_SETTLEMENT")
        return html.Div(
            [
                html.Strong(bl.get("bl_number")),
                html.P(f"Category: {category}", className="muted"),
                html.P(
                    f"Std min: {repository.money(calc.get('std_min_fee') or 0)} | "
                    f"Admin: {repository.money(calc.get('admin_fee') or 0)} | "
                    f"VAT: {repository.money(calc.get('vat') or 0)} | "
                    f"Total: {repository.money(calc.get('total') or 0)}"
                ),
            ],
            className="notice success",
        )
    except Exception as exc:  # noqa: BLE001
        return html.Div(str(exc), className="notice error")
