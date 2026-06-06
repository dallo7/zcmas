import dash_ag_grid as dag
from dash import Input, Output, State, callback, ctx, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate

from components.icons import icon
from components.layout import header, section_label
from services import auth, repository


register_page(__name__, path="/admin-support", name="Admin Support")


SUPPORT_STATUSES = ["Open", "In Progress", "Waiting on CFA", "Resolved"]
ADMIN_MANAGED_ROLES = {auth.ROLE_COMPANY_ADMIN, auth.ROLE_DECLARANT}


def _require_admin_support(user: dict | None) -> None:
    role = auth.normalize_role((user or {}).get("role"))
    if role not in {auth.ROLE_ADMIN, auth.ROLE_SUPER_ADMIN}:
        raise PermissionError("Admin Support access required.")


def _matches_search(row: dict, search: str | None) -> bool:
    term = (search or "").strip().lower()
    if not term:
        return True
    return term in " ".join(str(value or "") for value in row.values()).lower()


def _grid(grid_id: str, columns: list[dict], row_data: list[dict] | None = None, height: int = 330, selectable: bool = False):
    select_col = {
        "headerName": "",
        "field": "_select",
        "checkboxSelection": True,
        "headerCheckboxSelection": False,
        "width": 48,
        "pinned": "left",
        "sortable": False,
        "filter": False,
    }
    return dag.AgGrid(
        id=grid_id,
        className="ag-theme-alpine zcams-ag-grid admin-ag-grid admin-support-grid",
        columnDefs=([select_col] if selectable else []) + columns,
        rowData=row_data or [],
        defaultColDef={
            "sortable": True,
            "filter": True,
            "resizable": True,
            "wrapText": True,
            "autoHeight": True,
            "floatingFilter": True,
        },
        dashGridOptions={
            "rowSelection": "multiple",
            "rowMultiSelectWithClick": True,
            "suppressRowClickSelection": False,
            "animateRows": True,
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
            "pagination": True,
            "paginationPageSize": 10,
        },
        style={"height": f"{height}px", "width": "100%"},
    )


def _metric(title: str, value, icon_name: str, tone: str = "blue", detail: str = ""):
    return html.Div(
        [
            html.Div(icon(icon_name, 18), className=f"admin-metric-icon {tone}"),
            html.Div(
                [
                    html.Span(title, className="admin-metric-label"),
                    html.Strong(str(value), className="admin-metric-value"),
                    html.Small(detail, className="muted"),
                ],
                className="stack compact",
            ),
        ],
        className="admin-metric-card admin-support-metric",
    )


def _section_title(title: str, subtitle: str, icon_name: str):
    return html.Div(
        [
            html.Div(icon(icon_name, 22), className="admin-section-icon"),
            html.Div([html.H2(title), html.P(subtitle, className="muted section-lead")]),
        ],
        className="admin-section-title",
    )


def _search(search_id: str, placeholder: str):
    return html.Div(
        [
            icon("lucide:search", 15),
            dcc.Input(id=search_id, placeholder=placeholder, className="form-control admin-search-input"),
        ],
        className="admin-search-bar",
    )


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


def _managed_role_options():
    return [
        {"label": "Company Admin", "value": auth.ROLE_COMPANY_ADMIN},
        {"label": "Declarant / Agent", "value": auth.ROLE_DECLARANT},
    ]


def _company_options():
    return [
        {"label": company.get("name") or company["id"], "value": company["id"]}
        for company in repository.list_companies()
    ]


def _require_managed_role(role: str | None) -> str:
    normalized = auth.normalize_role(role)
    if normalized not in ADMIN_MANAGED_ROLES:
        raise ValueError("Admin Support can only manage Company Admin and Declarant users.")
    return normalized


def _selected_user_id(selected_rows: list[dict] | None) -> str:
    if not selected_rows:
        raise ValueError("Select one Company Admin or Declarant user first.")
    return selected_rows[0].get("id")


def _ticket_rows(search: str | None = None) -> list[dict]:
    return [
        {
            "id": ticket.get("id"),
            "created_at": (ticket.get("created_at") or "")[:19],
            "company_name": ticket.get("company_name") or ticket.get("company_id") or "-",
            "subject": ticket.get("subject") or "-",
            "description": ticket.get("description") or "-",
            "module": ticket.get("linked_module") or "-",
            "priority": ticket.get("priority") or "-",
            "status": ticket.get("status") or "-",
            "created_by": ticket.get("created_by_email") or ticket.get("created_by") or "-",
        }
        for ticket in repository.list_support_tickets(company_id=None, search=search)
    ]


def _user_rows(search: str | None = None) -> list[dict]:
    rows = []
    for user in repository.list_system_users(search):
        role = auth.normalize_role(user.get("role"))
        if role not in {auth.ROLE_COMPANY_ADMIN, auth.ROLE_DECLARANT}:
            continue
        rows.append(
            {
                **user,
                "name": f"{user.get('first_name') or ''} {user.get('last_name') or ''}".strip(),
                "role_label": auth.role_label(role),
            }
        )
    return rows


def _company_rows(search: str | None = None) -> list[dict]:
    return [row for row in repository.admin_support_company_readiness_rows() if _matches_search(row, search)]


def _activity_rows(search: str | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    logins = [
        {
            "created_at": (item.get("created_at") or "")[:19],
            "email": item.get("email") or item.get("user_email") or "-",
            "user": f"{item.get('first_name') or ''} {item.get('last_name') or ''}".strip() or "-",
            "role": auth.role_label(item.get("role")),
            "success": "Success" if item.get("success") else "Failed",
            "failure_reason": item.get("failure_reason") or "-",
            "ip_address": item.get("ip_address") or "-",
        }
        for item in auth.list_login_events(80)
        if auth.normalize_role(item.get("role")) in ADMIN_MANAGED_ROLES
    ]
    sessions = [
        {
            "last_seen_at": (item.get("last_seen_at") or "")[:19],
            "email": item.get("email") or "-",
            "role": auth.role_label(item.get("role")),
            "status": item.get("session_status") or "-",
            "ip_address": item.get("ip_address") or "-",
            "expires_at": (item.get("expires_at") or "")[:19],
        }
        for item in auth.list_user_sessions(80)
        if auth.normalize_role(item.get("role")) in ADMIN_MANAGED_ROLES
    ]
    audits = [
        {
            "created_at": (item.get("created_at") or "")[:19],
            "company_name": item.get("company_name") or item.get("company_id") or "-",
            "actor": item.get("actor_email") or "-",
            "action": item.get("action_type") or "-",
            "entity": item.get("entity_type") or "-",
            "details": item.get("details") or "-",
        }
        for item in auth.list_audit_events(80)
        if item.get("company_id")
    ]
    return (
        [row for row in logins if _matches_search(row, search)],
        [row for row in sessions if _matches_search(row, search)],
        [row for row in audits if _matches_search(row, search)],
    )


def _lookup_card(title: str, rows: list[html.Div | html.P | html.Strong | html.A]):
    return html.Div([html.H3(title), *rows], className="notice success admin-support-lookup-card")


def layout(**_kwargs):
    company_options = _company_options()
    default_company = company_options[0]["value"] if company_options else repository.DEMO_COMPANY_ID
    return html.Div(
        [
            header(
                "Admin Support Centre",
                help_text="Support CFA Admins and Declarants with diagnostics, tickets, shipment lookups, company readiness, and activity monitoring.",
                pathname="/admin-support",
            ),
            dcc.Store(id="admin-support-refresh", data=0),
            html.Div(
                [
                    html.Div(id="admin-support-summary", className="admin-dashboard-summary"),
                    html.Div(
                        [
                            _section_title("Support Queue", "Cross-CFA tickets with controlled status updates for support follow-up.", "lucide:life-buoy"),
                            html.Div(
                                [
                                    _search("admin-support-ticket-search", "Search tickets by company, subject, module, priority, status..."),
                                    dcc.Dropdown(
                                        id="admin-support-ticket-status",
                                        options=[{"label": status, "value": status} for status in SUPPORT_STATUSES],
                                        value="In Progress",
                                        clearable=False,
                                        className="admin-dropdown",
                                    ),
                                    html.Button([icon("lucide:check-circle", 14), "Update Status"], id="admin-support-ticket-update", className="btn-primary", type="button"),
                                ],
                                className="report-toolbar",
                            ),
                            html.Div(id="admin-support-ticket-message"),
                            _grid(
                                "admin-support-ticket-grid",
                                [
                                    {"headerName": "Created", "field": "created_at", "minWidth": 160},
                                    {"headerName": "Company", "field": "company_name", "minWidth": 200},
                                    {"headerName": "Subject", "field": "subject", "minWidth": 260, "flex": 1},
                                    {"headerName": "Module", "field": "module", "minWidth": 140},
                                    {"headerName": "Priority", "field": "priority", "minWidth": 120},
                                    {"headerName": "Status", "field": "status", "minWidth": 140},
                                    {"headerName": "Created By", "field": "created_by", "minWidth": 220},
                                ],
                                selectable=True,
                            ),
                        ],
                        className="card section-card stack admin-command-section",
                    ),
                    html.Div(
                        [
                            _section_title("Support Diagnostics", "Look up user access, shipment lifecycle, invoice payment state, and GN 83 context.", "lucide:stethoscope"),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H3("User Access Diagnostic"),
                                            html.P(
                                                "Check a Company Admin or Declarant account, status, company, and recent login attempts.",
                                                className="muted section-label-copy",
                                            ),
                                            dcc.Input(id="admin-support-user-query", placeholder="Email or username", className="form-control"),
                                            html.Button("Run user diagnostic", id="admin-support-user-run", className="btn-secondary", type="button"),
                                            html.Div(id="admin-support-user-result", className="stack compact"),
                                        ],
                                        className="card section-card stack admin-tool-card",
                                    ),
                                    html.Div(
                                        [
                                            html.H3("Shipment Resolver"),
                                            html.P(
                                                "Trace a BL, Z-SAD, invoice, or CapitalPay reference during a support investigation.",
                                                className="muted section-label-copy",
                                            ),
                                            dcc.Input(id="admin-support-shipment-query", placeholder="BL, Z-SAD, invoice, or CapitalPay reference", className="form-control"),
                                            html.Button("Resolve shipment", id="admin-support-shipment-run", className="btn-secondary", type="button"),
                                            html.Div(id="admin-support-shipment-result", className="stack compact"),
                                        ],
                                        className="card section-card stack admin-tool-card",
                                    ),
                                ],
                                className="admin-tools-row admin-tools-row-two",
                            ),
                        ],
                        className="stack",
                    ),
                    html.Div(
                        [
                            _section_title("Company Admin & Declarant Management", "Admin Support can read and write only Company Admin and Declarant users.", "lucide:users-round"),
                            html.Div(
                                [
                                    dcc.Dropdown(
                                        id="admin-support-managed-company",
                                        options=company_options,
                                        value=default_company,
                                        clearable=False,
                                        className="admin-dropdown",
                                    ),
                                    dcc.Input(id="admin-support-managed-first-name", placeholder="First name", className="form-control"),
                                    dcc.Input(id="admin-support-managed-last-name", placeholder="Last name", className="form-control"),
                                    dcc.Input(id="admin-support-managed-email", placeholder="Email", className="form-control"),
                                    dcc.Input(id="admin-support-managed-phone", placeholder="Phone", className="form-control"),
                                    dcc.Dropdown(
                                        id="admin-support-managed-role",
                                        options=_managed_role_options(),
                                        value=auth.ROLE_DECLARANT,
                                        clearable=False,
                                        className="admin-dropdown",
                                    ),
                                ],
                                className="admin-form-grid",
                            ),
                            html.Div(
                                [
                                    html.Button([icon("lucide:user-plus", 14), "Create"], id="admin-support-user-create", className="btn-primary", type="button"),
                                    html.Button([icon("lucide:save", 14), "Update Selected"], id="admin-support-user-update", className="btn-secondary", type="button"),
                                    html.Button([icon("lucide:user-check", 14), "Activate"], id="admin-support-user-activate", className="btn-secondary", type="button"),
                                    html.Button([icon("lucide:user-x", 14), "Suspend"], id="admin-support-user-suspend", className="btn-warning", type="button"),
                                    html.Button([icon("lucide:mail-check", 14), "Resend Email"], id="admin-support-user-resend-email", className="btn-secondary", type="button"),
                                    html.Button([icon("lucide:trash-2", 14), "Delete"], id="admin-support-user-delete", className="btn-danger", type="button"),
                                ],
                                className="row-actions admin-actions",
                            ),
                            html.Div(id="admin-support-user-action-message"),
                            html.Div(id="admin-support-resend-progress-live", children=_mail_progress()),
                            html.Div(id="admin-support-resend-progress", children=_mail_progress()),
                            _search("admin-support-user-search", "Search users by name, email, company, role, or status..."),
                            _grid(
                                "admin-support-users-grid",
                                [
                                    {"headerName": "Company", "field": "company_name", "minWidth": 210},
                                    {"headerName": "Name", "field": "name", "minWidth": 180},
                                    {"headerName": "Email", "field": "email", "minWidth": 230},
                                    {"headerName": "Role", "field": "role_label", "minWidth": 150},
                                    {"headerName": "Status", "field": "status", "minWidth": 130},
                                    {"headerName": "Phone", "field": "phone", "minWidth": 140},
                                    {"headerName": "Created", "field": "created_at", "minWidth": 170},
                                ],
                                selectable=True,
                            ),
                        ],
                        className="card section-card stack admin-command-section",
                    ),
                    html.Div(
                        [
                            _section_title("Company Readiness", "Profile, banking, certificate, ticket, and team readiness across CFAs.", "lucide:building-2"),
                            _search("admin-support-company-search", "Search CFA readiness by company, status, missing field, or banking state..."),
                            _grid(
                                "admin-support-company-grid",
                                [
                                    {"headerName": "Company", "field": "company_name", "minWidth": 230},
                                    {"headerName": "Status", "field": "status", "minWidth": 150},
                                    {"headerName": "Compliance", "field": "compliance_score", "minWidth": 130},
                                    {"headerName": "Banking Ready", "field": "banking_ready", "minWidth": 150},
                                    {"headerName": "Company Admins", "field": "company_admins", "minWidth": 150},
                                    {"headerName": "Declarants", "field": "declarants", "minWidth": 130},
                                    {"headerName": "Certificates", "field": "certificates", "minWidth": 130},
                                    {"headerName": "Open Tickets", "field": "open_tickets", "minWidth": 130},
                                    {"headerName": "Missing Fields", "field": "missing_fields", "minWidth": 300, "flex": 1},
                                ],
                                height=360,
                            ),
                        ],
                        className="card section-card stack admin-command-section",
                    ),
                    html.Div(
                        [
                            _section_title("Activity Monitor", "Recent login, session, and audit evidence for support investigations.", "lucide:activity"),
                            _search("admin-support-activity-search", "Search activity by email, role, action, company, status, or IP..."),
                            section_label(
                                "Recent Login Attempts",
                                "Shows successful and failed Company Admin or Declarant sign-in attempts with reason and IP evidence.",
                                "lucide:log-in",
                            ),
                            _grid(
                                "admin-support-logins-grid",
                                [
                                    {"headerName": "Time", "field": "created_at", "minWidth": 160},
                                    {"headerName": "Email", "field": "email", "minWidth": 230},
                                    {"headerName": "User", "field": "user", "minWidth": 170},
                                    {"headerName": "Role", "field": "role", "minWidth": 150},
                                    {"headerName": "Result", "field": "success", "minWidth": 120},
                                    {"headerName": "Reason", "field": "failure_reason", "minWidth": 200},
                                    {"headerName": "IP", "field": "ip_address", "minWidth": 150},
                                ],
                                height=260,
                            ),
                            section_label(
                                "User Sessions",
                                "Lists active, expired, and revoked sessions so support can confirm whether access is still live.",
                                "lucide:monitor-check",
                            ),
                            _grid(
                                "admin-support-sessions-grid",
                                [
                                    {"headerName": "Last Seen", "field": "last_seen_at", "minWidth": 160},
                                    {"headerName": "Email", "field": "email", "minWidth": 230},
                                    {"headerName": "Role", "field": "role", "minWidth": 150},
                                    {"headerName": "Status", "field": "status", "minWidth": 120},
                                    {"headerName": "IP", "field": "ip_address", "minWidth": 150},
                                    {"headerName": "Expires", "field": "expires_at", "minWidth": 170},
                                ],
                                height=240,
                            ),
                            section_label(
                                "Audit Trail",
                                "Captures user, ticket, and workflow changes that support may need to explain or escalate.",
                                "lucide:scroll-text",
                            ),
                            _grid(
                                "admin-support-audit-grid",
                                [
                                    {"headerName": "Time", "field": "created_at", "minWidth": 160},
                                    {"headerName": "Company", "field": "company_name", "minWidth": 220},
                                    {"headerName": "Actor", "field": "actor", "minWidth": 220},
                                    {"headerName": "Action", "field": "action", "minWidth": 180},
                                    {"headerName": "Entity", "field": "entity", "minWidth": 140},
                                    {"headerName": "Details", "field": "details", "minWidth": 320, "flex": 1},
                                ],
                                height=300,
                            ),
                        ],
                        className="card section-card stack admin-command-section",
                    ),
                ],
                className="page-content stack admin-support-page",
            ),
        ]
    )


@callback(
    Output("admin-support-summary", "children"),
    Input("auth-user", "data"),
    Input("admin-support-refresh", "data"),
    Input("_pages_location", "pathname"),
)
def render_admin_support_summary(user, _refresh, pathname):
    if (pathname or "") != "/admin-support":
        raise PreventUpdate
    _require_admin_support(user)
    summary = repository.admin_support_summary()
    return html.Div(
        [
            html.Div(
                [
                    html.H2("Admin Support Command Centre"),
                    html.P(
                        "Purpose-built for helping CFA Admins and Declarants without Super Admin platform-control powers.",
                        className="muted",
                    ),
                ],
                className="admin-hero-copy",
            ),
            html.Div(
                [
                    _metric("Open Tickets", summary.get("open_tickets"), "lucide:life-buoy", "amber", "Needs support action"),
                    _metric("Failed Logins", summary.get("failed_logins"), "lucide:shield-alert", "red", "Access diagnostics"),
                    _metric("Active Sessions", summary.get("active_sessions"), "lucide:activity", "blue", "Read-only visibility"),
                    _metric("Outstanding Invoices", summary.get("outstanding_invoices"), "lucide:receipt", "purple", "Payment follow-up"),
                    _metric("Pending BL Review", summary.get("pending_bls"), "lucide:file-clock", "green", "Declarant workflow support"),
                ],
                className="admin-metrics-grid",
            ),
        ],
        className="admin-hero card section-card",
    )


@callback(
    Output("admin-support-ticket-grid", "rowData"),
    Input("admin-support-ticket-search", "value"),
    Input("admin-support-refresh", "data"),
    Input("auth-user", "data"),
    Input("_pages_location", "pathname"),
)
def render_admin_support_tickets(search, _refresh, user, pathname):
    if (pathname or "") != "/admin-support":
        raise PreventUpdate
    _require_admin_support(user)
    return _ticket_rows(search)


@callback(
    Output("admin-support-ticket-message", "children"),
    Output("admin-support-refresh", "data"),
    Input("admin-support-ticket-update", "n_clicks"),
    State("admin-support-ticket-grid", "selectedRows"),
    State("admin-support-ticket-status", "value"),
    State("auth-user", "data"),
    State("admin-support-refresh", "data"),
    prevent_initial_call=True,
    running=[
        (
            Output("admin-support-resend-progress-live", "children"),
            _mail_progress("Sending login credentials. Please wait...", 68, "sending"),
            _mail_progress(),
        )
    ],
)
def update_admin_support_ticket(_clicks, selected_rows, status, user, refresh):
    try:
        _require_admin_support(user)
        if not selected_rows:
            return _notice("Select one support ticket first.", "error"), no_update
        ticket_id = selected_rows[0].get("id")
        repository.update_ticket_status(ticket_id, status or "In Progress")
        return _notice(f"Ticket status updated to {status}."), (refresh or 0) + 1
    except Exception as exc:  # noqa: BLE001
        return _notice(str(exc), "error"), no_update


@callback(
    Output("admin-support-users-grid", "rowData"),
    Input("admin-support-user-search", "value"),
    Input("admin-support-refresh", "data"),
    Input("auth-user", "data"),
    Input("_pages_location", "pathname"),
)
def render_admin_support_users(search, _refresh, user, pathname):
    if (pathname or "") != "/admin-support":
        raise PreventUpdate
    _require_admin_support(user)
    return _user_rows(search)


@callback(
    Output("admin-support-managed-company", "value"),
    Output("admin-support-managed-first-name", "value"),
    Output("admin-support-managed-last-name", "value"),
    Output("admin-support-managed-email", "value"),
    Output("admin-support-managed-phone", "value"),
    Output("admin-support-managed-role", "value"),
    Input("admin-support-users-grid", "selectedRows"),
    prevent_initial_call=True,
)
def load_selected_admin_support_user(selected_rows):
    if not selected_rows:
        raise PreventUpdate
    selected = selected_rows[0]
    _require_managed_role(selected.get("role"))
    return (
        selected.get("company_id") or repository.DEMO_COMPANY_ID,
        selected.get("first_name") or "",
        selected.get("last_name") or "",
        selected.get("email") or "",
        selected.get("phone") or "",
        selected.get("role") or auth.ROLE_DECLARANT,
    )


@callback(
    Output("admin-support-user-action-message", "children"),
    Output("admin-support-resend-progress", "children"),
    Output("admin-support-refresh", "data", allow_duplicate=True),
    Output("admin-support-managed-first-name", "value", allow_duplicate=True),
    Output("admin-support-managed-last-name", "value", allow_duplicate=True),
    Output("admin-support-managed-email", "value", allow_duplicate=True),
    Output("admin-support-managed-phone", "value", allow_duplicate=True),
    Input("admin-support-user-create", "n_clicks"),
    Input("admin-support-user-update", "n_clicks"),
    Input("admin-support-user-activate", "n_clicks"),
    Input("admin-support-user-suspend", "n_clicks"),
    Input("admin-support-user-resend-email", "n_clicks"),
    Input("admin-support-user-delete", "n_clicks"),
    State("admin-support-users-grid", "selectedRows"),
    State("admin-support-managed-company", "value"),
    State("admin-support-managed-first-name", "value"),
    State("admin-support-managed-last-name", "value"),
    State("admin-support-managed-email", "value"),
    State("admin-support-managed-phone", "value"),
    State("admin-support-managed-role", "value"),
    State("auth-user", "data"),
    State("admin-support-refresh", "data"),
    prevent_initial_call=True,
)
def apply_admin_support_user_action(
    _create,
    _update,
    _activate,
    _suspend,
    _resend,
    _delete,
    selected_rows,
    company_id,
    first,
    last,
    email,
    phone,
    role,
    user,
    refresh,
):
    clear_values = [no_update, no_update, no_update, no_update]
    try:
        _require_admin_support(user)
        action = ctx.triggered_id
        if action == "admin-support-user-create":
            managed_role = _require_managed_role(role)
            created = repository.create_system_user(
                company_id=company_id or repository.DEMO_COMPANY_ID,
                first_name=(first or "").strip(),
                last_name=(last or "").strip(),
                email=(email or "").strip(),
                role=managed_role,
                phone=(phone or "").strip(),
            )
            clear_values = ["", "", "", ""]
            if created.get("email_result", {}).get("sent"):
                message = f"Created {auth.role_label(managed_role)} user {created.get('email')}. Credentials were emailed."
                return _notice(message), _mail_progress(), (refresh or 0) + 1, *clear_values
            message = f"Created {auth.role_label(managed_role)} user {created.get('email')}. Email was not confirmed; temporary password: {created.get('temp_password')}"
            return _notice(message, "error"), _mail_progress(), (refresh or 0) + 1, *clear_values

        selected_id = _selected_user_id(selected_rows)
        existing = repository.get_system_user(selected_id)
        _require_managed_role(existing.get("role"))
        if action == "admin-support-user-update":
            managed_role = _require_managed_role(role)
            updated = repository.update_system_user(
                selected_id,
                company_id or existing.get("company_id") or repository.DEMO_COMPANY_ID,
                (first or "").strip(),
                (last or "").strip(),
                (email or "").strip(),
                managed_role,
                phone=(phone or "").strip(),
                username=existing.get("username") or "",
            )
            return _notice(f"Updated {updated.get('email')}."), _mail_progress(), (refresh or 0) + 1, *clear_values
        if action == "admin-support-user-delete":
            repository.delete_system_user(selected_id)
            return _notice("Selected Company Admin/Declarant user deleted."), _mail_progress(), (refresh or 0) + 1, *clear_values
        if action == "admin-support-user-resend-email":
            target_ids = [row.get("id") for row in (selected_rows or []) if row.get("id")] or [selected_id]
            sent = []
            failed = []
            for target_id in target_ids:
                existing = repository.get_system_user(target_id)
                _require_managed_role(existing.get("role"))
                delivery = repository.resend_user_credentials(
                    target_id,
                    source="admin-support-resend",
                    actor_role=auth.ROLE_ADMIN,
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
                    *clear_values,
                )
            return (
                _notice(f"Credentials resent to {len(sent)} user(s). Each user must set a new password on first login."),
                _mail_progress(f"Mail sent to {len(sent)} user(s).", 100, "success"),
                (refresh or 0) + 1,
                *clear_values,
            )
        status = "SUSPENDED" if action == "admin-support-user-suspend" else "ACTIVE"
        updated = repository.set_system_user_status(selected_id, status)
        return _notice(f"{updated.get('email')} is now {updated.get('status')}."), _mail_progress(), (refresh or 0) + 1, *clear_values
    except Exception as exc:  # noqa: BLE001
        return _notice(str(exc), "error"), _mail_progress("Resend failed before mail could be sent.", 100, "error"), no_update, *clear_values


@callback(
    Output("admin-support-company-grid", "rowData"),
    Input("admin-support-company-search", "value"),
    Input("admin-support-refresh", "data"),
    Input("auth-user", "data"),
    Input("_pages_location", "pathname"),
)
def render_admin_support_companies(search, _refresh, user, pathname):
    if (pathname or "") != "/admin-support":
        raise PreventUpdate
    _require_admin_support(user)
    return _company_rows(search)


@callback(
    Output("admin-support-logins-grid", "rowData"),
    Output("admin-support-sessions-grid", "rowData"),
    Output("admin-support-audit-grid", "rowData"),
    Input("admin-support-activity-search", "value"),
    Input("admin-support-refresh", "data"),
    Input("auth-user", "data"),
    Input("_pages_location", "pathname"),
)
def render_admin_support_activity(search, _refresh, user, pathname):
    if (pathname or "") != "/admin-support":
        raise PreventUpdate
    _require_admin_support(user)
    return _activity_rows(search)


@callback(
    Output("admin-support-user-result", "children"),
    Input("admin-support-user-run", "n_clicks"),
    State("admin-support-user-query", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def run_admin_support_user_lookup(_clicks, query, user):
    try:
        _require_admin_support(user)
        result = auth.cs_lookup_user(query)
        if result.get("error"):
            return _notice(result["error"], "error")
        found = result["user"]
        _require_managed_role(found.get("role"))
        logins = result.get("recent_logins") or []
        return _lookup_card(
            "User Access Result",
            [
                html.Strong(f"{found.get('first_name')} {found.get('last_name')}"),
                html.P(f"{auth.role_label(found.get('role'))} | {found.get('status')} | {found.get('email')}", className="muted"),
                html.P(f"Company: {found.get('company_name') or '-'} ({found.get('company_status') or '-'})"),
                html.Ul(
                    [
                        html.Li(
                            f"{(login.get('created_at') or '')[:19]} - "
                            f"{'OK' if login.get('success') else 'Failed'} - "
                            f"{login.get('ip_address') or '-'} - {login.get('failure_reason') or ''}"
                        )
                        for login in logins
                    ]
                )
                if logins
                else html.P("No recent login events.", className="muted"),
            ],
        )
    except Exception as exc:  # noqa: BLE001
        return _notice(str(exc), "error")


@callback(
    Output("admin-support-shipment-result", "children"),
    Input("admin-support-shipment-run", "n_clicks"),
    State("admin-support-shipment-query", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def run_admin_support_shipment_lookup(_clicks, query, user):
    try:
        _require_admin_support(user)
        q = (query or "").strip()
        result = auth.cs_lookup_shipment(q)
        bl = result.get("bl") if not result.get("error") else None
        if not bl:
            inv = repository.row(
                """
                SELECT inv.*, bl.bl_number, bl.company_id, c.name AS company_name,
                       pay.status AS payment_status, pay.capitalpay_ref, pay.secure_link
                FROM invoices inv
                JOIN reviewed_bls rb ON rb.id = inv.reviewed_bl_id
                JOIN bills_of_lading bl ON bl.id = rb.bl_id
                LEFT JOIN companies c ON c.id = bl.company_id
                LEFT JOIN payments pay ON pay.invoice_id = inv.id
                WHERE inv.invoice_number = ?
                   OR inv.capitalpay_urn = ?
                   OR pay.capitalpay_ref = ?
                ORDER BY inv.created_at DESC
                LIMIT 1
                """,
                (q, q, q),
            )
            if not inv:
                return _notice(result.get("error") or f"No shipment found for '{q}'.", "error")
            return _lookup_card(
                "Payment & Invoice Result",
                [
                    html.Strong(inv.get("invoice_number")),
                    html.P(f"Company: {inv.get('company_name') or '-'} | BL: {inv.get('bl_number') or '-'}", className="muted"),
                    html.P(f"Invoice: {inv.get('status') or '-'} | Payment: {inv.get('payment_status') or '-'} | Total: {repository.money(inv.get('total') or 0)}"),
                    html.P(f"CapitalPay: {inv.get('capitalpay_urn') or inv.get('capitalpay_ref') or '-'}"),
                    html.A("Open checkout", href=inv.get("checkout_url") or inv.get("secure_link"), target="_blank", className="text-link")
                    if inv.get("checkout_url") or inv.get("secure_link")
                    else html.P("No checkout link available.", className="muted"),
                ],
            )
        return _lookup_card(
            "Shipment Result",
            [
                html.Strong(bl.get("bl_number")),
                html.P(f"Company: {bl.get('company_name') or '-'} | Consignee: {bl.get('consignee_name') or '-'}", className="muted"),
                html.P(f"BL status: {bl.get('status') or '-'} | Reviewed: {bl.get('reviewed_status') or '-'}"),
                html.P(f"Z-SAD: {bl.get('z_sad_number') or '-'} | Invoice: {bl.get('invoice_number') or '-'}"),
                html.P(f"Invoice status: {bl.get('invoice_status') or '-'} | Payment: {bl.get('payment_status') or '-'}"),
            ],
        )
    except Exception as exc:  # noqa: BLE001
        return _notice(str(exc), "error")
