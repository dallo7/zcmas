import dash_ag_grid as dag
from dash import Input, Output, State, callback, dash_table, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate

from components.icons import icon
from components.layout import header
from services import auth, repository


register_page(__name__, path="/super-admin", name="Super Admin")


def _metric(label: str, value, *, icon_name: str, tone: str = "green", accent: str = "var(--zambia-green)"):
    return html.Div(
        [
            html.Div(
                [
                    html.Span(icon(icon_name, 15), className="super-admin-metric-icon"),
                    html.Div(str(value), className="update-stat-value", style={"color": accent}),
                ],
                className="super-admin-metric-top",
            ),
            html.Div(label, className="update-stat-label"),
        ],
        className=f"update-stat-card super-admin-metric-card metric-{tone}",
    )


def _section_heading(title: str, icon_name: str, *, tone: str = "green"):
    return html.Div(
        [
            html.Span(icon(icon_name, 16), className=f"section-heading-icon tone-{tone}"),
            html.H2(title),
        ],
        className="section-heading-with-icon",
    )


def _cute_data_table_kwargs(page_size: int = 8) -> dict:
    return {
        "page_size": page_size,
        "cell_selectable": True,
        "include_headers_on_copy_paste": True,
        "style_table": {"overflowX": "auto", "borderRadius": "16px", "border": "1px solid #e6efe7"},
        "style_header": {
            "backgroundColor": "#F3FAF4",
            "color": "#203227",
            "fontWeight": "700",
            "border": "0",
            "textTransform": "uppercase",
            "letterSpacing": "0.04em",
            "fontSize": "11px",
        },
        "style_cell": {
            "border": "0",
            "borderBottom": "1px solid #E8EFE9",
            "padding": "10px 12px",
            "fontFamily": "inherit",
            "fontSize": "12px",
            "whiteSpace": "normal",
            "height": "auto",
        },
        "style_data_conditional": [
            {"if": {"row_index": "odd"}, "backgroundColor": "#F8FBF7"},
            {"if": {"state": "active"}, "backgroundColor": "#FFF8E1", "border": "1px solid #FCD116"},
        ],
    }


def _ag_grid(
    grid_id: str,
    columns: list[dict],
    rows: list[dict],
    *,
    row_class_rules: dict | None = None,
):
    selectable_columns = [
        {
            "headerName": "Select",
            "field": "__select__",
            "width": 86,
            "checkboxSelection": True,
            "headerCheckboxSelection": True,
            "sortable": False,
            "filter": False,
            "floatingFilter": False,
            "resizable": False,
            "suppressSizeToFit": True,
        },
        *columns,
    ]
    return dag.AgGrid(
        id=grid_id,
        columnDefs=selectable_columns,
        rowData=rows,
        selectedRows=[],
        defaultColDef={
            "sortable": True,
            "filter": True,
            "resizable": True,
            "wrapText": True,
            "autoHeight": True,
            "floatingFilter": True,
        },
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": 10,
            "animateRows": True,
            "domLayout": "autoHeight",
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
            "rowSelection": "multiple",
            "suppressRowClickSelection": True,
        },
        rowClassRules=row_class_rules or {},
        className="ag-theme-alpine zcams-ag-grid",
    )


def _chat_report_rows(search: str | None = None) -> list[dict]:
    return [
        {
            "created_at": (item.get("created_at") or "")[:19],
            "company_name": item.get("company_name") or "-",
            "user_email": item.get("user_email") or "-",
            "role": (item.get("user_role") or "").replace("_", " ").title() or "-",
            "question": item.get("question") or "",
            "answer": item.get("answer") or "",
            "mode": item.get("mode") or "-",
            "quality": item.get("quality") or "Neutral Response",
        }
        for item in repository.list_chat_events(search=search)
    ]


def _support_report_rows(search: str | None = None) -> list[dict]:
    return [
        {
            "created_at": (ticket.get("created_at") or "")[:19],
            "company_name": ticket.get("company_name") or ticket.get("company_id") or "-",
            "subject": ticket.get("subject") or "",
            "description": ticket.get("description") or "",
            "module": ticket.get("linked_module") or "-",
            "priority": ticket.get("priority") or "-",
            "status": ticket.get("status") or "-",
            "created_by": ticket.get("created_by_email") or ticket.get("created_by") or "-",
            "resolved_at": (ticket.get("resolved_at") or "")[:19],
        }
        for ticket in repository.list_support_tickets(search=search)
    ]


def _notification_report_rows(search: str | None = None) -> list[dict]:
    notes = repository.list_notifications(company_id=None)
    if search:
        q = search.strip().lower()
        notes = [
            note
            for note in notes
            if q
            in " ".join(
                str(note.get(field) or "")
                for field in ("event_type", "message", "company_name", "created_at", "related_entity_id")
            ).lower()
        ]
    return [
        {
            "created_at": (note.get("created_at") or "")[:19],
            "company_name": note.get("company_name") or note.get("company_id") or "-",
            "event_type": (note.get("event_type") or "").replace("_", " ").title(),
            "message": note.get("message") or "",
            "read": "Read" if int(note.get("is_read") or 0) else "Unread",
            "related_entity_id": note.get("related_entity_id") or "-",
        }
        for note in notes
    ]


def _company_options() -> list[dict]:
    return [{"label": company.get("name") or company["id"], "value": company["id"]} for company in repository.list_companies()]


def _company_report_rows() -> list[dict]:
    return [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "company_email": c.get("company_email"),
            "status": c.get("status"),
            "created_at": (c.get("created_at") or "")[:19],
        }
        for c in repository.list_companies()
    ]


def _session_report_rows() -> list[dict]:
    return [
        {
            "id": s.get("id"),
            "email": s.get("email"),
            "role": (s.get("role") or "").replace("_", " ").title(),
            "status": s.get("session_status") or "ACTIVE",
            "ip_address": s.get("ip_address") or "-",
            "last_seen_at": (s.get("last_seen_at") or "")[:19],
            "expires_at": (s.get("expires_at") or "")[:19],
            "revoked_at": (s.get("revoked_at") or "")[:19],
        }
        for s in auth.list_user_sessions(50)
    ]


def _select_options(rows: list[dict], label_fields: tuple[str, ...]) -> list[dict]:
    options = []
    for item in rows:
        label_parts = [str(item.get(field) or "") for field in label_fields if item.get(field)]
        options.append({"label": " - ".join(label_parts) or item.get("id"), "value": item.get("id")})
    return options


def _user_report_rows(search: str | None = None) -> list[dict]:
    return [
        {
            "id": user.get("id"),
            "company_id": user.get("company_id"),
            "first_name": user.get("first_name") or "",
            "last_name": user.get("last_name") or "",
            "raw_role": user.get("role") or "",
            "created_at": (user.get("created_at") or "")[:19],
            "company_name": user.get("company_name") or user.get("company_id") or "-",
            "name": f"{user.get('first_name') or ''} {user.get('last_name') or ''}".strip(),
            "username": user.get("username") or "-",
            "email": user.get("email") or "",
            "role": (user.get("role") or "").replace("_", " ").title(),
            "status": user.get("status") or "-",
            "phone": user.get("phone") or "-",
        }
        for user in repository.list_system_users(search=search)
    ]


def layout(**_kwargs):
    stats = repository.dashboard_stats()
    pending = [c for c in repository.list_companies() if c.get("status") == "PENDING_APPROVAL"]
    company_options = _company_options()
    default_company = company_options[0]["value"] if company_options else repository.DEMO_COMPANY_ID
    return html.Div(
        [
            header(
                "Platform Control Centre",
                help_text="ZAFFA Super Admin oversight: CFA approvals, sessions, audit trail, and cross-tenant transactions.",
                pathname="/super-admin",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            _metric("Registered CFAs", stats.get("companies", 0), icon_name="lucide:building-2", tone="green"),
                            _metric(
                                "Pending approvals",
                                len(pending),
                                icon_name="lucide:badge-alert",
                                tone="orange",
                                accent="var(--zambia-orange)",
                            ),
                            _metric(
                                "BLs (all tenants)",
                                stats.get("bls", 0),
                                icon_name="lucide:file-stack",
                                tone="yellow",
                                accent="var(--zambia-yellow)",
                            ),
                            _metric(
                                "Outstanding invoices",
                                stats.get("outstanding_invoices", 0),
                                icon_name="lucide:receipt-text",
                                tone="red",
                                accent="var(--zambia-red)",
                            ),
                            _metric(
                                "Active sessions",
                                len(auth.list_active_sessions(100)),
                                icon_name="lucide:activity",
                                tone="blue",
                                accent="#0033A0",
                            ),
                            _metric(
                                "Unread notifications",
                                stats.get("notifications_unread", 0),
                                icon_name="lucide:bell-ring",
                                tone="purple",
                                accent="#7c3aed",
                            ),
                        ],
                        className="update-stat-grid",
                    ),
                    html.Div(id="super-admin-action-result"),
                    html.Div(
                        [
                            _section_heading("User Management", "lucide:users-round", tone="blue"),
                            html.P(
                                "Create any ZCAMS user and assign Super Admin, Company Admin, or Declarant permissions.",
                                className="muted section-lead",
                            ),
                            html.Div(id="super-admin-user-result"),
                            dcc.Dropdown(
                                id="super-admin-user-picker",
                                options=_select_options(_user_report_rows(), ("name", "email", "role", "status")),
                                placeholder="Select a user before update, suspend, activate, or delete",
                                className="form-control super-admin-picker",
                            ),
                            html.Div(
                                [
                                    dcc.Input(id="super-user-first-name", placeholder="First name", className="form-control"),
                                    dcc.Input(id="super-user-last-name", placeholder="Last name", className="form-control"),
                                    dcc.Input(id="super-user-email", placeholder="Email", className="form-control"),
                                    dcc.Input(id="super-user-username", placeholder="Username (optional)", className="form-control"),
                                    dcc.Dropdown(
                                        id="super-user-company",
                                        options=company_options,
                                        value=default_company,
                                        className="form-control",
                                    ),
                                    dcc.Dropdown(
                                        id="super-user-role",
                                        options=[
                                            {"label": "Super Admin", "value": auth.ROLE_SUPER_ADMIN},
                                            {"label": "Company Admin", "value": auth.ROLE_COMPANY_ADMIN},
                                            {"label": "Declarant / Agent", "value": auth.ROLE_DECLARANT},
                                        ],
                                        value=auth.ROLE_DECLARANT,
                                        className="form-control",
                                    ),
                                    dcc.Input(id="super-user-phone", placeholder="Phone", className="form-control"),
                                    dcc.Input(
                                        id="super-user-password",
                                        placeholder="Password (optional, generated if blank)",
                                        type="password",
                                        className="form-control",
                                    ),
                                ],
                                className="form-grid compact-form-grid",
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        [icon("lucide:user-plus", 14), "Create User"],
                                        id="super-admin-create-user",
                                        className="btn-primary",
                                        type="button",
                                    ),
                                    html.Button(
                                        [icon("lucide:save", 14), "Update"],
                                        id="super-admin-update-user",
                                        className="btn-secondary",
                                        type="button",
                                    ),
                                    html.Button(
                                        [icon("lucide:user-x", 14), "Suspend"],
                                        id="super-admin-suspend-user",
                                        className="btn-secondary",
                                        type="button",
                                    ),
                                    html.Button(
                                        [icon("lucide:user-check", 14), "Activate"],
                                        id="super-admin-activate-user",
                                        className="btn-secondary",
                                        type="button",
                                    ),
                                    html.Button(
                                        [icon("lucide:trash-2", 14), "Delete"],
                                        id="super-admin-delete-user",
                                        className="btn-danger",
                                        type="button",
                                    ),
                                    dcc.Input(
                                        id="super-admin-user-search",
                                        placeholder="Search users by name, email, role, status, company...",
                                        className="form-control report-search",
                                    ),
                                ],
                                className="report-toolbar",
                            ),
                            _ag_grid(
                                "super-admin-users-grid",
                                [
                                    {"headerName": "Created", "field": "created_at", "width": 150},
                                    {"headerName": "Company", "field": "company_name", "width": 190},
                                    {"headerName": "Name", "field": "name", "width": 170},
                                    {"headerName": "Username", "field": "username", "width": 150},
                                    {"headerName": "Email", "field": "email", "width": 210},
                                    {"headerName": "Role", "field": "role", "width": 150},
                                    {"headerName": "Status", "field": "status", "width": 120},
                                    {"headerName": "Phone", "field": "phone", "width": 140},
                                ],
                                _user_report_rows(),
                                row_class_rules={
                                    "user-super-row": "params.data.role === 'Super Admin'",
                                    "user-admin-row": "params.data.role === 'Company Admin'",
                                    "user-declarant-row": "params.data.role === 'Declarant'",
                                },
                            ),
                        ],
                        className="card section-card stack super-admin-compact-card",
                        id="users",
                    ),
                    html.Div(
                        [
                            _section_heading("CFA Registry & Onboarding Queue", "lucide:building", tone="green"),
                            html.P(
                                "Approve pending CFA registrations. Approved companies receive login credentials by email.",
                                className="muted section-lead",
                            ),
                            dcc.Dropdown(
                                id="super-admin-company-picker",
                                options=_select_options(_company_report_rows(), ("name", "company_email", "status")),
                                placeholder="Select a CFA before taking action",
                                className="form-control super-admin-picker",
                            ),
                            html.Div(
                                [
                                    dcc.Input(id="super-company-name", placeholder="CFA company name", className="form-control"),
                                    dcc.Input(id="super-company-email", placeholder="Company email", className="form-control"),
                                    dcc.Input(id="super-company-phone", placeholder="Company phone", className="form-control"),
                                ],
                                className="form-grid compact-form-grid",
                            ),
                            _ag_grid(
                                "super-admin-companies-table",
                                [
                                    {"headerName": "Company", "field": "name", "flex": 1},
                                    {"headerName": "Email", "field": "company_email", "width": 230},
                                    {"headerName": "Status", "field": "status", "width": 160},
                                    {"headerName": "Created", "field": "created_at", "width": 170},
                                    {"headerName": "ID", "field": "id", "width": 180},
                                ],
                                _company_report_rows(),
                                row_class_rules={
                                    "company-pending-row": "params.data.status === 'PENDING_APPROVAL'",
                                    "company-approved-row": "params.data.status === 'APPROVED'",
                                },
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        [icon("lucide:badge-check", 14), "Approve selected CFA"],
                                        id="super-admin-approve-company",
                                        className="btn-primary",
                                        type="button",
                                    ),
                                    html.Button(
                                        [icon("lucide:save", 14), "Update"],
                                        id="super-admin-update-company",
                                        className="btn-secondary",
                                        type="button",
                                    ),
                                    html.Button(
                                        [icon("lucide:building-x", 14), "Suspend"],
                                        id="super-admin-suspend-company",
                                        className="btn-secondary",
                                        type="button",
                                    ),
                                    html.Button(
                                        [icon("lucide:building-check", 14), "Activate"],
                                        id="super-admin-activate-company",
                                        className="btn-secondary",
                                        type="button",
                                    ),
                                    html.Button(
                                        [icon("lucide:trash-2", 14), "Delete"],
                                        id="super-admin-delete-company",
                                        className="btn-danger",
                                        type="button",
                                    ),
                                    html.Button(
                                        [icon("lucide:refresh-cw", 14), "Refresh"],
                                        id="super-admin-refresh",
                                        className="btn-secondary",
                                        type="button",
                                    ),
                                ],
                                className="row-actions",
                            ),
                        ],
                        className="card section-card stack",
                        id="companies",
                    ),
                    html.Div(
                        [
                            _section_heading("Login & Session Monitor", "lucide:monitor-check", tone="blue"),
                            dcc.Dropdown(
                                id="super-admin-session-picker",
                                options=_select_options(_session_report_rows(), ("email", "status", "last_seen_at")),
                                placeholder="Select a login session before revoke, restore, or delete",
                                className="form-control super-admin-picker",
                            ),
                            _ag_grid(
                                "super-admin-sessions-table",
                                [
                                    {"headerName": "User", "field": "email", "width": 230},
                                    {"headerName": "Role", "field": "role", "width": 150},
                                    {"headerName": "Status", "field": "status", "width": 130},
                                    {"headerName": "IP", "field": "ip_address", "width": 140},
                                    {"headerName": "Last Seen", "field": "last_seen_at", "width": 170},
                                    {"headerName": "Expires", "field": "expires_at", "width": 170},
                                    {"headerName": "Revoked", "field": "revoked_at", "width": 170},
                                ],
                                _session_report_rows(),
                                row_class_rules={
                                    "session-active-row": "params.data.status === 'ACTIVE'",
                                    "session-revoked-row": "params.data.status === 'REVOKED'",
                                    "session-expired-row": "params.data.status === 'EXPIRED'",
                                },
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        [icon("lucide:shield-off", 14), "Revoke"],
                                        id="super-admin-revoke-session",
                                        className="btn-secondary",
                                        type="button",
                                    ),
                                    html.Button(
                                        [icon("lucide:rotate-ccw", 14), "Restore"],
                                        id="super-admin-restore-session",
                                        className="btn-secondary",
                                        type="button",
                                    ),
                                    html.Button(
                                        [icon("lucide:trash-2", 14), "Delete"],
                                        id="super-admin-delete-session",
                                        className="btn-danger",
                                        type="button",
                                    ),
                                ],
                                className="row-actions",
                            ),
                            html.H3([icon("lucide:history", 14), " Recent sign-in activity"], className="inline-icon-heading"),
                            dash_table.DataTable(
                                columns=[
                                    {"name": "When", "id": "created_at"},
                                    {"name": "Email", "id": "email"},
                                    {"name": "User", "id": "user_label"},
                                    {"name": "Success", "id": "success_label"},
                                    {"name": "IP", "id": "ip_address"},
                                ],
                                data=[
                                    {
                                        "created_at": (e.get("created_at") or "")[:19],
                                        "email": e.get("email") or "-",
                                        "user_label": f"{e.get('first_name') or ''} {e.get('last_name') or ''}".strip() or "-",
                                        "success_label": "Yes" if e.get("success") else "No",
                                        "ip_address": e.get("ip_address") or "-",
                                    }
                                    for e in auth.list_login_events(25)
                                ],
                                **_cute_data_table_kwargs(8),
                            ),
                        ],
                        className="card section-card stack",
                        id="sessions",
                    ),
                    html.Div(
                        [
                            _section_heading("Platform Audit Log", "lucide:scroll-text", tone="purple"),
                            dash_table.DataTable(
                                columns=[
                                    {"name": "When", "id": "created_at"},
                                    {"name": "Action", "id": "action_type"},
                                    {"name": "Company", "id": "company_name"},
                                    {"name": "Actor", "id": "actor"},
                                    {"name": "Entity", "id": "entity_type"},
                                    {"name": "Details", "id": "details"},
                                ],
                                data=[
                                    {
                                        "created_at": (a.get("created_at") or "")[:19],
                                        "action_type": a.get("action_type"),
                                        "company_name": a.get("company_name") or a.get("company_id") or "-",
                                        "actor": f"{a.get('first_name') or ''} {a.get('last_name') or ''}".strip()
                                        or a.get("actor_email")
                                        or a.get("user_id"),
                                        "entity_type": a.get("entity_type"),
                                        "details": (a.get("details") or "")[:120],
                                    }
                                    for a in auth.list_audit_events(40)
                                ],
                                **_cute_data_table_kwargs(10),
                            ),
                        ],
                        className="card section-card stack",
                        id="audit",
                    ),
                    html.Div(
                        [
                            _section_heading("Cross-Tenant Transaction Monitor", "lucide:git-branch", tone="orange"),
                            dash_table.DataTable(
                                columns=[
                                    {"name": "Company", "id": "company_name"},
                                    {"name": "BL", "id": "bl_number"},
                                    {"name": "BL status", "id": "bl_status"},
                                    {"name": "Reviewed", "id": "reviewed_status"},
                                    {"name": "Z-SAD", "id": "z_sad_number"},
                                    {"name": "Invoice", "id": "invoice_number"},
                                    {"name": "Invoice status", "id": "invoice_status"},
                                    {"name": "Payment", "id": "payment_status"},
                                ],
                                data=[
                                    {
                                        "company_name": t.get("company_name") or t.get("company_id"),
                                        "bl_number": t.get("bl_number"),
                                        "bl_status": t.get("bl_status"),
                                        "reviewed_status": t.get("reviewed_status") or "-",
                                        "z_sad_number": t.get("z_sad_number") or "-",
                                        "invoice_number": t.get("invoice_number") or "-",
                                        "invoice_status": t.get("invoice_status") or "-",
                                        "payment_status": t.get("payment_status") or "-",
                                    }
                                    for t in auth.platform_transaction_rows(35)
                                ],
                                **_cute_data_table_kwargs(10),
                            ),
                        ],
                        className="card section-card stack",
                        id="transactions",
                    ),
                    html.Div(
                        [
                            _section_heading("Support Command Centre", "lucide:life-buoy", tone="red"),
                            html.P("Platform-wide support report for every ticket raised in ZCAMS.", className="muted section-lead"),
                            dcc.Input(
                                id="super-admin-support-search",
                                placeholder="Search support tickets by company, subject, module, priority, status...",
                                className="form-control report-search",
                            ),
                            _ag_grid(
                                "super-admin-support-grid",
                                [
                                    {"headerName": "Created", "field": "created_at", "width": 160},
                                    {"headerName": "Company", "field": "company_name", "width": 190},
                                    {"headerName": "Subject", "field": "subject", "flex": 1},
                                    {"headerName": "Description", "field": "description", "flex": 2},
                                    {"headerName": "Module", "field": "module", "width": 130},
                                    {"headerName": "Priority", "field": "priority", "width": 120},
                                    {"headerName": "Status", "field": "status", "width": 120},
                                    {"headerName": "Created By", "field": "created_by", "width": 190},
                                ],
                                _support_report_rows(),
                                row_class_rules={
                                    "ticket-open-row": "params.data.status === 'Open'",
                                    "ticket-resolved-row": "params.data.status === 'Resolved'",
                                },
                            ),
                        ],
                        className="card section-card stack",
                        id="support",
                    ),
                    html.Div(
                        [
                            _section_heading("Notifications Report", "lucide:bell-ring", tone="purple"),
                            html.P("Search platform notifications across onboarding, BLs, Z-SADs, invoices, payments, cargo release, contracts, and support.", className="muted section-lead"),
                            dcc.Input(
                                id="super-admin-notifications-search",
                                placeholder="Search notifications by event, message, company, entity...",
                                className="form-control report-search",
                            ),
                            _ag_grid(
                                "super-admin-notifications-grid",
                                [
                                    {"headerName": "Created", "field": "created_at", "width": 160},
                                    {"headerName": "Company", "field": "company_name", "width": 190},
                                    {"headerName": "Event", "field": "event_type", "width": 180},
                                    {"headerName": "Message", "field": "message", "flex": 2},
                                    {"headerName": "Read", "field": "read", "width": 100},
                                    {"headerName": "Entity", "field": "related_entity_id", "width": 180},
                                ],
                                _notification_report_rows(),
                                row_class_rules={"notification-unread-row": "params.data.read === 'Unread'"},
                            ),
                        ],
                        className="card section-card stack",
                        id="notifications-report",
                    ),
                    html.Div(
                        [
                            _section_heading("ZCAMS Chat Report", "lucide:bot-message-square", tone="green"),
                            html.P(
                                "All captured questions and answers from ZCAMS Chat, classified as Good Response, Bad Response, or Neutral Response.",
                                className="muted section-lead",
                            ),
                            html.Div(
                                [
                                    dcc.Input(
                                        id="super-admin-chat-search",
                                        placeholder="Search chat questions, answers, mode, quality, user, company...",
                                        className="form-control report-search",
                                    ),
                                    dcc.Upload(
                                        id="super-admin-chat-context-upload",
                                        children=html.Button(
                                            [icon("lucide:upload-cloud", 14), "Upload Model Context"],
                                            className="btn-secondary",
                                            type="button",
                                        ),
                                        multiple=False,
                                    ),
                                ],
                                className="report-toolbar",
                            ),
                            html.Div(id="super-admin-chat-upload-result"),
                            _ag_grid(
                                "super-admin-chat-grid",
                                [
                                    {"headerName": "Created", "field": "created_at", "width": 160},
                                    {"headerName": "Company", "field": "company_name", "width": 190},
                                    {"headerName": "User", "field": "user_email", "width": 210},
                                    {"headerName": "Role", "field": "role", "width": 140},
                                    {"headerName": "Question", "field": "question", "flex": 2},
                                    {"headerName": "Answer", "field": "answer", "flex": 3},
                                    {"headerName": "Mode", "field": "mode", "width": 130},
                                    {"headerName": "Quality", "field": "quality", "width": 150},
                                ],
                                _chat_report_rows(),
                                row_class_rules={
                                    "chat-good-row": "params.data.quality === 'Good Response'",
                                    "chat-bad-row": "params.data.quality === 'Bad Response'",
                                    "chat-neutral-row": "params.data.quality === 'Neutral Response'",
                                },
                            ),
                        ],
                        className="card section-card stack",
                        id="chat-report",
                    ),
                ],
                className="page-content stack",
            ),
        ]
    )


def _require_super_admin(user: dict | None):
    if not user or user.get("role") != auth.ROLE_SUPER_ADMIN:
        raise PermissionError("Super Admin access required.")


@callback(
    Output("super-admin-action-result", "children"),
    Output("super-admin-company-picker", "options"),
    Output("super-admin-companies-table", "rowData"),
    Input("super-admin-approve-company", "n_clicks"),
    Input("super-admin-refresh", "n_clicks"),
    State("super-admin-company-picker", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def super_admin_company_actions(_approve_clicks, _refresh, selected_company_id, user):
    from dash import ctx

    trigger = ctx.triggered_id
    notice = no_update
    try:
        _require_super_admin(user)
        if trigger == "super-admin-approve-company":
            if not selected_company_id:
                notice = html.Div("Select a CFA row to approve.", className="notice error")
            else:
                result = repository.approve_company(selected_company_id)
                name = result.get("company", {}).get("name") or selected_company_id
                notice = html.Div(f"Approved {name}. Credentials emailed where configured.", className="notice success")
    except PermissionError as exc:
        notice = html.Div(str(exc), className="notice error")
    except Exception as exc:  # noqa: BLE001
        notice = html.Div(str(exc), className="notice error")

    company_rows = _company_report_rows()
    return notice, _select_options(company_rows, ("name", "company_email", "status")), company_rows


@callback(
    Output("super-company-name", "value"),
    Output("super-company-email", "value"),
    Output("super-company-phone", "value"),
    Input("super-admin-company-picker", "value"),
    prevent_initial_call=True,
)
def load_selected_super_admin_company(company_id):
    company = repository.get_company(company_id) if company_id else {}
    if not company:
        raise PreventUpdate
    return company.get("name") or "", company.get("company_email") or "", company.get("phone") or ""


@callback(
    Output("super-admin-action-result", "children", allow_duplicate=True),
    Output("super-admin-company-picker", "options", allow_duplicate=True),
    Output("super-admin-companies-table", "rowData", allow_duplicate=True),
    Input("super-admin-update-company", "n_clicks"),
    Input("super-admin-suspend-company", "n_clicks"),
    Input("super-admin-activate-company", "n_clicks"),
    Input("super-admin-delete-company", "n_clicks"),
    State("super-admin-company-picker", "value"),
    State("super-company-name", "value"),
    State("super-company-email", "value"),
    State("super-company-phone", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def super_admin_registry_company_actions(
    _update_clicks,
    _suspend_clicks,
    _activate_clicks,
    _delete_clicks,
    selected_company_id,
    name,
    email,
    phone,
    user,
):
    from dash import ctx

    notice = no_update
    try:
        _require_super_admin(user)
        if not selected_company_id:
            raise ValueError("Select a CFA first.")
        trigger = ctx.triggered_id
        if trigger == "super-admin-update-company":
            updated = repository.update_registry_company(selected_company_id, name or "", email or "", phone or "")
            notice = html.Div(f"Updated {updated.get('name')}.", className="notice success")
        elif trigger == "super-admin-suspend-company":
            updated = repository.set_registry_company_status(selected_company_id, "SUSPENDED")
            notice = html.Div(f"Suspended {updated.get('name')}.", className="notice success")
        elif trigger == "super-admin-activate-company":
            updated = repository.set_registry_company_status(selected_company_id, "APPROVED")
            notice = html.Div(f"Activated {updated.get('name')}.", className="notice success")
        elif trigger == "super-admin-delete-company":
            repository.delete_registry_company(selected_company_id)
            notice = html.Div("CFA company deleted.", className="notice success")
    except Exception as exc:  # noqa: BLE001
        notice = html.Div(str(exc), className="notice error")
    company_rows = _company_report_rows()
    return notice, _select_options(company_rows, ("name", "company_email", "status")), company_rows


@callback(
    Output("super-admin-action-result", "children", allow_duplicate=True),
    Output("super-admin-session-picker", "options"),
    Output("super-admin-sessions-table", "rowData"),
    Input("super-admin-revoke-session", "n_clicks"),
    Input("super-admin-restore-session", "n_clicks"),
    Input("super-admin-delete-session", "n_clicks"),
    State("super-admin-session-picker", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def super_admin_session_actions(_revoke_clicks, _restore_clicks, _delete_clicks, selected_session_id, user):
    from dash import ctx

    notice = no_update
    try:
        _require_super_admin(user)
        if not selected_session_id:
            notice = html.Div("Select a session first.", className="notice error")
        elif ctx.triggered_id == "super-admin-revoke-session":
            auth.revoke_user_session(selected_session_id)
            notice = html.Div("Session revoked.", className="notice success")
        elif ctx.triggered_id == "super-admin-restore-session":
            auth.restore_user_session(selected_session_id)
            notice = html.Div("Session restored and expiry extended.", className="notice success")
        elif ctx.triggered_id == "super-admin-delete-session":
            auth.delete_user_session(selected_session_id)
            notice = html.Div("Session deleted.", className="notice success")
    except PermissionError as exc:
        notice = html.Div(str(exc), className="notice error")
    except Exception as exc:  # noqa: BLE001
        notice = html.Div(str(exc), className="notice error")

    session_rows = _session_report_rows()
    return notice, _select_options(session_rows, ("email", "status", "last_seen_at")), session_rows


@callback(
    Output("super-admin-user-result", "children"),
    Output("super-admin-user-picker", "options"),
    Output("super-admin-users-grid", "rowData"),
    Output("super-user-first-name", "value"),
    Output("super-user-last-name", "value"),
    Output("super-user-email", "value"),
    Output("super-user-username", "value"),
    Output("super-user-phone", "value"),
    Output("super-user-password", "value"),
    Input("super-admin-create-user", "n_clicks"),
    Input("super-admin-user-search", "value"),
    State("super-user-company", "value"),
    State("super-user-role", "value"),
    State("super-user-first-name", "value"),
    State("super-user-last-name", "value"),
    State("super-user-email", "value"),
    State("super-user-username", "value"),
    State("super-user-phone", "value"),
    State("super-user-password", "value"),
    State("auth-user", "data"),
    prevent_initial_call=False,
)
def manage_super_admin_users(
    _create_clicks,
    search,
    company_id,
    role,
    first_name,
    last_name,
    email,
    username,
    phone,
    password,
    current_user,
):
    from dash import ctx

    notice = no_update
    clear_values = [no_update, no_update, no_update, no_update, no_update, no_update]
    if ctx.triggered_id == "super-admin-user-search":
        user_rows = _user_report_rows(search)
        return no_update, _select_options(user_rows, ("name", "email", "role", "status")), user_rows, *clear_values
    if ctx.triggered_id == "super-admin-create-user":
        try:
            _require_super_admin(current_user)
            created = repository.create_system_user(
                company_id=company_id or repository.DEMO_COMPANY_ID,
                first_name=(first_name or "").strip(),
                last_name=(last_name or "").strip(),
                email=(email or "").strip(),
                username=(username or "").strip(),
                phone=(phone or "").strip(),
                role=role or auth.ROLE_DECLARANT,
                password=(password or "").strip(),
            )
            notice = html.Div(
                [
                    html.Strong("User created. "),
                    html.Span(f"Username: {created.get('username')}. "),
                    html.Span(
                        "Credentials were emailed and the user must set a new password on first login."
                        if created.get("email_result", {}).get("sent")
                        else f"Email was not confirmed; temporary password: {created.get('temp_password')}",
                    ),
                ],
                className="notice success",
            )
            clear_values = ["", "", "", "", "", ""]
        except Exception as exc:  # noqa: BLE001
            notice = html.Div(str(exc), className="notice error")
    user_rows = _user_report_rows(search)
    return notice, _select_options(user_rows, ("name", "email", "role", "status")), user_rows, *clear_values


@callback(
    Output("super-user-first-name", "value", allow_duplicate=True),
    Output("super-user-last-name", "value", allow_duplicate=True),
    Output("super-user-email", "value", allow_duplicate=True),
    Output("super-user-username", "value", allow_duplicate=True),
    Output("super-user-company", "value"),
    Output("super-user-role", "value"),
    Output("super-user-phone", "value", allow_duplicate=True),
    Output("super-user-password", "value", allow_duplicate=True),
    Input("super-admin-user-picker", "value"),
    prevent_initial_call=True,
)
def load_selected_super_admin_user(selected_user_id):
    row = repository.get_system_user(selected_user_id) if selected_user_id else {}
    if not row.get("id"):
        raise PreventUpdate
    return (
        row.get("first_name") or "",
        row.get("last_name") or "",
        row.get("email") or "",
        row.get("username") or "",
        row.get("company_id") or repository.DEMO_COMPANY_ID,
        row.get("role") or auth.ROLE_DECLARANT,
        row.get("phone") or "",
        "",
    )


@callback(
    Output("super-admin-user-result", "children", allow_duplicate=True),
    Output("super-admin-user-picker", "options", allow_duplicate=True),
    Output("super-admin-users-grid", "rowData", allow_duplicate=True),
    Input("super-admin-update-user", "n_clicks"),
    Input("super-admin-suspend-user", "n_clicks"),
    Input("super-admin-activate-user", "n_clicks"),
    Input("super-admin-delete-user", "n_clicks"),
    State("super-admin-user-picker", "value"),
    State("super-admin-user-search", "value"),
    State("super-user-company", "value"),
    State("super-user-role", "value"),
    State("super-user-first-name", "value"),
    State("super-user-last-name", "value"),
    State("super-user-email", "value"),
    State("super-user-username", "value"),
    State("super-user-phone", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def apply_super_admin_user_action(
    _update_clicks,
    _suspend_clicks,
    _activate_clicks,
    _delete_clicks,
    selected_id,
    search,
    company_id,
    role,
    first_name,
    last_name,
    email,
    username,
    phone,
    current_user,
):
    from dash import ctx

    trigger = ctx.triggered_id
    if not selected_id:
        user_rows = _user_report_rows(search)
        return (
            html.Div("Select a user first.", className="notice error"),
            _select_options(user_rows, ("name", "email", "role", "status")),
            user_rows,
        )
    try:
        _require_super_admin(current_user)
        if trigger in {"super-admin-suspend-user", "super-admin-delete-user"} and selected_id == (current_user or {}).get("id"):
            raise ValueError("You cannot suspend or delete your own active Super Admin session.")
        if trigger == "super-admin-update-user":
            updated = repository.update_system_user(
                selected_id,
                company_id or repository.DEMO_COMPANY_ID,
                (first_name or "").strip(),
                (last_name or "").strip(),
                (email or "").strip(),
                role or auth.ROLE_DECLARANT,
                phone=(phone or "").strip(),
                username=(username or "").strip(),
            )
            notice = html.Div(f"Updated {updated.get('email')}.", className="notice success")
        elif trigger == "super-admin-suspend-user":
            updated = repository.set_system_user_status(selected_id, "SUSPENDED")
            notice = html.Div(f"Suspended {updated.get('email')}.", className="notice success")
        elif trigger == "super-admin-activate-user":
            updated = repository.set_system_user_status(selected_id, "ACTIVE")
            notice = html.Div(f"Activated {updated.get('email')}.", className="notice success")
        elif trigger == "super-admin-delete-user":
            repository.delete_system_user(selected_id)
            notice = html.Div("User deleted.", className="notice success")
        else:
            raise PreventUpdate
    except PreventUpdate:
        raise
    except Exception as exc:  # noqa: BLE001
        notice = html.Div(str(exc), className="notice error")
    user_rows = _user_report_rows(search)
    return notice, _select_options(user_rows, ("name", "email", "role", "status")), user_rows


@callback(
    Output("super-admin-support-grid", "rowData"),
    Input("super-admin-support-search", "value"),
    Input("_pages_location", "pathname"),
    prevent_initial_call=False,
)
def update_super_admin_support_report(search, pathname):
    if (pathname or "").split("#", 1)[0] != "/super-admin":
        raise PreventUpdate
    return _support_report_rows(search)


@callback(
    Output("super-admin-notifications-grid", "rowData"),
    Input("super-admin-notifications-search", "value"),
    Input("_pages_location", "pathname"),
    prevent_initial_call=False,
)
def update_super_admin_notifications_report(search, pathname):
    if (pathname or "").split("#", 1)[0] != "/super-admin":
        raise PreventUpdate
    return _notification_report_rows(search)


@callback(
    Output("super-admin-chat-upload-result", "children"),
    Output("super-admin-chat-grid", "rowData"),
    Input("super-admin-chat-search", "value"),
    Input("super-admin-chat-context-upload", "contents"),
    State("super-admin-chat-context-upload", "filename"),
    State("auth-user", "data"),
    State("_pages_location", "pathname"),
    prevent_initial_call=False,
)
def update_super_admin_chat_report(search, contents, filename, user, pathname):
    if (pathname or "").split("#", 1)[0] != "/super-admin":
        raise PreventUpdate
    notice = no_update
    if contents:
        try:
            uploaded = repository.save_chat_context_upload(filename or "zcams-context.txt", contents, user=user)
            notice = html.Div(
                f"Context uploaded: {uploaded['file_name']} ({uploaded['size']:,} bytes). Future chat answers can retrieve it.",
                className="notice success",
            )
        except Exception as exc:  # noqa: BLE001
            notice = html.Div(str(exc), className="notice error")
    return notice, _chat_report_rows(search)
