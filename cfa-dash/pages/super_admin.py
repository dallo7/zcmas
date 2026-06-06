import ipaddress

import dash_ag_grid as dag
import requests
from dash import ALL, Input, Output, State, callback, ctx, dash_table, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate

from components.icons import icon
from components.layout import header, section_label
from services import auth, repository
from services.bulk_registration import parse_bulk_registration_upload


register_page(__name__, path="/super-admin", name="Super Admin")

_GEO_IP_CACHE: dict[str, dict] = {}


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


def _mail_progress(label: str = "Waiting for resend action.", percent: int = 0, state: str = "idle"):
    visible = state != "idle"
    return html.Div(
        [
            html.Div(
                [
                    html.Span(label),
                    html.Span(f"{max(0, min(100, int(percent)))}%"),
                ],
                className="mail-progress-label",
            ),
            html.Div(
                html.Div(style={"width": f"{max(0, min(100, int(percent)))}%"}, className="mail-progress-fill"),
                className="mail-progress-track",
            ),
        ],
        className=f"mail-progress {state}{' is-visible' if visible else ''}",
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
            "rowMultiSelectWithClick": True,
            "suppressRowClickSelection": False,
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


def _network_label(ip_address: str | None) -> str:
    ip = (ip_address or "").strip()
    if not ip or ip == "-":
        return "Unknown location"
    if ip in {"127.0.0.1", "::1"}:
        return "Local device"
    if ip.startswith(("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31.")):
        return "Private network"
    return "Public network"


def _is_public_ip(ip_address: str | None) -> bool:
    try:
        parsed = ipaddress.ip_address((ip_address or "").strip())
    except ValueError:
        return False
    return not (parsed.is_private or parsed.is_loopback or parsed.is_reserved or parsed.is_multicast)


def _geo_lookup_ip(ip_address: str | None) -> dict:
    ip = (ip_address or "").strip()
    if not ip or ip == "-":
        return {"status": "fail", "message": "No IP address was captured."}
    if not _is_public_ip(ip):
        return {
            "status": "local",
            "query": ip,
            "label": _network_label(ip),
            "message": "This IP is local/private, so public geo coordinates are not available.",
        }
    if ip in _GEO_IP_CACHE:
        return _GEO_IP_CACHE[ip]
    try:
        response = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,message,country,regionName,city,lat,lon,isp,query,timezone"},
            timeout=3,
        )
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        data = {"status": "fail", "query": ip, "message": f"Geo lookup unavailable: {exc}"}
    _GEO_IP_CACHE[ip] = data
    return data


def _geo_map_embed(lat: float, lon: float) -> html.Iframe:
    delta = 0.04
    bbox = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"
    return html.Iframe(
        src=f"https://www.openstreetmap.org/export/embed.html?bbox={bbox}&layer=mapnik&marker={lat},{lon}",
        className="ip-geo-map-frame",
        title="IP geo map",
    )


def _ip_geo_modal(ip_address: str | None, close_type: str = "super-admin-ip-geo-close") -> html.Div:
    ip = (ip_address or "").strip() or "-"
    geo = _geo_lookup_ip(ip)
    has_coordinates = geo.get("status") == "success" and geo.get("lat") is not None and geo.get("lon") is not None
    location_label = ", ".join(
        part for part in (geo.get("city"), geo.get("regionName"), geo.get("country")) if part
    ) or geo.get("label") or _network_label(ip)
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(icon("lucide:map-pinned", 18), className="login-visibility-icon"),
                            html.Div([html.H2("IP Geo Location"), html.P(f"Location lookup for {ip}", className="muted")]),
                        ],
                        className="modal-title-row",
                    ),
                    html.Button(
                        "x",
                        id={"type": close_type, "ip": ip},
                        className="modal-close",
                        type="button",
                    ),
                ],
                className="modal-header",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3([icon("lucide:crosshair", 15), " IP Details"]),
                            html.Div([html.Span("IP address"), html.Strong(ip)]),
                            html.Div([html.Span("Network type"), html.Strong(_network_label(ip))]),
                            html.Div([html.Span("Location"), html.Strong(location_label)]),
                            html.Div([html.Span("ISP"), html.Strong(geo.get("isp") or "-")]),
                            html.Div([html.Span("Timezone"), html.Strong(geo.get("timezone") or "-")]),
                        ],
                        className="login-detail-card",
                    ),
                    html.Div(
                        _geo_map_embed(float(geo["lat"]), float(geo["lon"]))
                        if has_coordinates
                        else html.Div(
                            [
                                icon("lucide:map", 32),
                                html.Strong(location_label),
                                html.Span(geo.get("message") or "No public map coordinates are available for this IP."),
                            ],
                            className="ip-geo-map-placeholder",
                        ),
                        className="ip-geo-map-card",
                    ),
                ],
                className="login-detail-grid",
            ),
        ],
        className="invoice-modal-card login-visibility-modal-card ip-geo-modal-card",
    )


def _device_label(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if not ua:
        return "Unknown device"
    device = "Mobile" if any(token in ua for token in ("mobile", "android", "iphone")) else "Desktop"
    if "edg/" in ua:
        browser = "Edge"
    elif "chrome/" in ua:
        browser = "Chrome"
    elif "firefox/" in ua:
        browser = "Firefox"
    elif "safari/" in ua:
        browser = "Safari"
    else:
        browser = "Browser"
    return f"{device} - {browser}"


def _login_visibility_data(session_id: str | None = None) -> dict:
    selected = None
    params: tuple = ()
    where_clause = "1 = 1"
    if session_id:
        selected = repository.row(
            """
            SELECT s.*, u.first_name, u.last_name, u.email, u.username, u.role, u.company_id, c.name AS company_name
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN companies c ON c.id = u.company_id
            WHERE s.id = ?
            """,
            (session_id,),
        )
    if selected:
        where_clause = "(le.user_id = ? OR lower(le.email) = lower(?))"
        params = (selected["user_id"], selected.get("email") or "")
    events = repository.rows(
        f"""
        SELECT le.*, u.first_name, u.last_name, u.username, u.email AS user_email, u.role, c.name AS company_name
        FROM login_events le
        LEFT JOIN users u ON u.id = le.user_id
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE {where_clause}
        ORDER BY le.created_at DESC
        LIMIT 80
        """,
        params,
    )
    sessions = auth.list_user_sessions(100)
    active_sessions = [item for item in sessions if item.get("session_status") == "ACTIVE"]
    unique_ips = {item.get("ip_address") for item in events if item.get("ip_address")}
    success_count = sum(1 for item in events if int(item.get("success") or 0))
    failed_count = sum(1 for item in events if not int(item.get("success") or 0))
    return {
        "selected": selected,
        "events": events,
        "summary": {
            "events": len(events),
            "successful": success_count,
            "failed": failed_count,
            "unique_ips": len(unique_ips),
            "active_sessions": len(active_sessions),
        },
    }


def _login_visibility_modal(session_id: str | None = None) -> html.Div:
    data = _login_visibility_data(session_id)
    selected = data["selected"]
    events = data["events"]
    summary = data["summary"]
    latest = selected or (events[0] if events else {})
    actor_name = f"{latest.get('first_name') or ''} {latest.get('last_name') or ''}".strip() or latest.get("email") or "Unknown user"
    actor_email = latest.get("email") or latest.get("user_email") or "-"
    actor_role = (latest.get("role") or "-").replace("_", " ").title()
    actor_ip = latest.get("ip_address") or "-"
    actor_device = _device_label(latest.get("user_agent"))
    event_rows = [
        [
            (item.get("created_at") or "-")[:19],
            item.get("company_name") or "-",
            item.get("user_email") or item.get("email") or "-",
            "Success" if int(item.get("success") or 0) else "Failed",
            item.get("ip_address") or "-",
            _network_label(item.get("ip_address")),
            _device_label(item.get("user_agent")),
            item.get("failure_reason") or "-",
        ]
        for item in events[:30]
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(icon("lucide:map-pinned", 18), className="login-visibility-icon"),
                            html.Div(
                                [
                                    html.H2("Login Visibility"),
                                    html.P("Who signed in, from where, and how often.", className="muted"),
                                ]
                            ),
                        ],
                        className="modal-title-row",
                    ),
                    html.Button("x", id="super-admin-login-visibility-close", className="modal-close", type="button"),
                ],
                className="modal-header",
            ),
            html.Div(
                [
                    html.Div([html.Strong(str(summary["events"])), html.Span("Tracked attempts")], className="login-analytics-card info"),
                    html.Div([html.Strong(str(summary["successful"])), html.Span("Successful logins")], className="login-analytics-card success"),
                    html.Div([html.Strong(str(summary["failed"])), html.Span("Failed attempts")], className="login-analytics-card danger" if summary["failed"] else "login-analytics-card"),
                    html.Div([html.Strong(str(summary["unique_ips"])), html.Span("Unique IPs")], className="login-analytics-card warning"),
                    html.Div([html.Strong(str(summary["active_sessions"])), html.Span("Active sessions")], className="login-analytics-card blue"),
                ],
                className="login-analytics-grid",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3([icon("lucide:user-round-check", 15), " Actor"]),
                            html.Div([html.Span("Name"), html.Strong(actor_name)]),
                            html.Div([html.Span("Email"), html.Strong(actor_email)]),
                            html.Div([html.Span("Role"), html.Strong(actor_role)]),
                            html.Div([html.Span("Company"), html.Strong(latest.get("company_name") or "-")]),
                        ],
                        className="login-detail-card",
                    ),
                    html.Div(
                        [
                            html.H3([icon("lucide:crosshair", 15), " Action Location"]),
                            html.Div([html.Span("IP address"), html.Strong(actor_ip)]),
                            html.Div([html.Span("Location"), html.Strong(_network_label(actor_ip))]),
                            html.Div([html.Span("Device"), html.Strong(actor_device)]),
                            html.P("Geo lookup is not enabled, so ZCAMS shows the captured IP/network type and browser/device fingerprint.", className="muted"),
                        ],
                        className="login-detail-card map-card",
                    ),
                ],
                className="login-detail-grid",
            ),
            html.Div(
                [
                    html.H3([icon("lucide:history", 15), " Detailed login trail"]),
                    _bulk_visibility_table(
                        ["Time", "Company", "Email", "Result", "IP", "Location", "Device", "Reason"],
                        event_rows,
                    ),
                ],
                className="login-trail-section",
            ),
        ],
        className="invoice-modal-card login-visibility-modal-card",
    )


def _recent_signin_activity_table() -> html.Div:
    events = auth.list_login_events(25)
    total = len(events)
    successful = sum(1 for event in events if int(event.get("success") or 0))
    failed = total - successful
    captured_ips = [event.get("ip_address") for event in events if event.get("ip_address")]
    unique_ips = len(set(captured_ips))
    local_private = sum(1 for ip in captured_ips if _network_label(ip) in {"Local device", "Private network"})
    public_ips = sum(1 for ip in captured_ips if _network_label(ip) == "Public network")
    rows_data = []
    for index, event in enumerate(events):
        ip_address = event.get("ip_address") or "-"
        success = bool(event.get("success"))
        rows_data.append(
            html.Tr(
                [
                    html.Td((event.get("created_at") or "")[:19]),
                    html.Td(event.get("email") or "-"),
                    html.Td(f"{event.get('first_name') or ''} {event.get('last_name') or ''}".strip() or "-"),
                    html.Td(
                        html.Span(
                            "Yes" if success else "No",
                            className="signin-status-pill success" if success else "signin-status-pill danger",
                        )
                    ),
                    html.Td(
                        html.Div(
                            [
                                html.Span(ip_address),
                                html.Button(
                                    icon("lucide:eye", 14),
                                    id={"type": "super-admin-ip-geo-open", "ip": ip_address, "index": index},
                                    n_clicks=0,
                                    className="ip-eye-button",
                                    title=f"View geo map for {ip_address}",
                                    type="button",
                                    **{"aria-label": f"View geo map for {ip_address}"},
                                ),
                            ],
                            className="ip-cell-action",
                        )
                    ),
                ],
                className="signin-row-success" if success else "signin-row-failed",
            )
        )
    return html.Div(
        [
            html.Div(
                [
                    html.Div([html.Strong(str(total)), html.Span("Recent attempts")], className="signin-kpi-card info"),
                    html.Div([html.Strong(str(successful)), html.Span("Successful")], className="signin-kpi-card success"),
                    html.Div([html.Strong(str(failed)), html.Span("Failed")], className="signin-kpi-card danger" if failed else "signin-kpi-card"),
                    html.Div([html.Strong(str(unique_ips)), html.Span("Unique IPs")], className="signin-kpi-card warning"),
                    html.Div([html.Strong(str(local_private)), html.Span("Local/private")], className="signin-kpi-card local"),
                    html.Div([html.Strong(str(public_ips)), html.Span("Public IPs")], className="signin-kpi-card blue"),
                ],
                className="signin-kpi-grid",
            ),
            html.Div(
                html.Table(
                    [
                        html.Thead(html.Tr([html.Th(label) for label in ("When", "Email", "User", "Success", "IP")])),
                        html.Tbody(rows_data or [html.Tr([html.Td("No login activity yet.", colSpan=5, className="muted")])]),
                    ],
                    className="bulk-visibility-table signin-activity-table",
                ),
                className="bulk-visibility-table-wrap",
            ),
            ],
        className="signin-activity-panel",
    )


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


def _selected_user_id_from_grid(selected_id: str | None, selected_rows: list[dict] | None, *, prefer_grid: bool = True) -> str | None:
    if prefer_grid and selected_rows:
        return selected_rows[0].get("id")
    if selected_id:
        return selected_id
    if selected_rows:
        return selected_rows[0].get("id")
    return None


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
                                "Create any ZCAMS user and assign Super Admin, Admin Support, Operations, Company Admin, or Declarant permissions.",
                                className="muted section-lead",
                            ),
                            html.Div(id="super-admin-user-result"),
                            html.Div(id="super-admin-resend-progress-live", children=_mail_progress()),
                            html.Div(id="super-admin-resend-progress", children=_mail_progress()),
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
                                            {"label": "Admin Support", "value": auth.ROLE_ADMIN},
                                            {"label": "Operations", "value": auth.ROLE_OPERATIONS},
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
                                        [icon("lucide:mail-check", 14), "Resend Email"],
                                        id="super-admin-resend-user-email",
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
                                    "user-support-admin-row": "params.data.role === 'Admin Support'",
                                    "user-operations-row": "params.data.role === 'Operations'",
                                    "user-admin-row": "params.data.role === 'Company Admin'",
                                    "user-declarant-row": "params.data.role === 'Declarant / Agent'",
                                },
                            ),
                        ],
                        className="card section-card stack super-admin-compact-card",
                        id="users",
                    ),
                    html.Div(
                        [
                            _section_heading("Bulk CFA Auto Registration", "lucide:file-up", tone="green"),
                            html.P(
                                "Upload CFA registration files to create or enforce Company Admin accounts only. "
                                "ZCAMS emails fresh login credentials to every processed CFA admin through the configured mail API.",
                                className="muted section-lead",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H3([icon("lucide:upload-cloud", 15), " Company Admin bulk upload"]),
                                            html.P(
                                                "Supported files: CSV, XLSX, TXT, DOC/DOCX, and PDF. Required information is a CFA company name and admin email; names, phone, PACRA, TPIN, ZRA licence, and ZAFFA number are used when present.",
                                                className="muted",
                                            ),
                                        ],
                                        className="stack compact",
                                    ),
                                    dcc.Upload(
                                        id="super-admin-bulk-cfa-upload",
                                        children=html.Button(
                                            [icon("lucide:file-up", 14), "Upload CFA Registration File"],
                                            className="btn-primary",
                                            type="button",
                                        ),
                                        accept=".csv,.txt,.xlsx,.xls,.doc,.docx,.pdf",
                                        multiple=False,
                                    ),
                                ],
                                className="bulk-registration-panel",
                            ),
                            html.Div(id="super-admin-bulk-file-preview", className="bulk-file-preview"),
                            html.Div(
                                [
                                    html.Div(
                                        html.Div(id="super-admin-bulk-progress-fill", className="bulk-progress-fill"),
                                        className="bulk-progress-track",
                                    ),
                                    html.Div("Waiting for upload.", id="super-admin-bulk-progress-text", className="bulk-progress-text"),
                                ],
                                className="bulk-progress-shell",
                            ),
                            html.Div(id="super-admin-bulk-cfa-result"),
                            html.Div(id="super-admin-bulk-visibility", children=_bulk_visibility_panel()),
                            html.Div(id="super-admin-bulk-ip-geo-modal", className="modal-backdrop is-hidden"),
                        ],
                        className="card section-card stack",
                        id="bulk-registration",
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
                            html.P(
                                "Review platform sessions, inspect login visibility, and revoke or restore suspicious access.",
                                className="muted section-lead",
                            ),
                            section_label(
                                "Session Register",
                                "Lists active, expired, and revoked sessions with user, role, IP address, last seen time, and expiry.",
                                "lucide:monitor-check",
                            ),
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
                                        [icon("lucide:eye", 14), "View Login Visibility"],
                                        id="super-admin-login-visibility-open",
                                        className="btn-primary",
                                        type="button",
                                    ),
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
                            html.Div(id="super-admin-login-visibility-modal", className="modal-backdrop is-hidden"),
                            html.Div(id="super-admin-activity-ip-geo-modal", className="modal-backdrop is-hidden"),
                            section_label(
                                "Recent Sign-in Activity",
                                "Shows the latest successful and failed login attempts so Super Admin can investigate account access.",
                                "lucide:history",
                            ),
                            _recent_signin_activity_table(),
                        ],
                        className="card section-card stack",
                        id="sessions",
                    ),
                    html.Div(
                        [
                            _section_heading("Platform Audit Log", "lucide:scroll-text", tone="purple"),
                            html.P(
                                "Immutable evidence of platform actions, actors, entities, and affected companies.",
                                className="muted section-lead",
                            ),
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
                            html.P(
                                "End-to-end shipment status across companies, from BL capture through Z-SAD, invoice, and payment.",
                                className="muted section-lead",
                            ),
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
                            html.P("Platform-wide support report for every ticket raised in ZCAMS, including module, priority, status, and creator.", className="muted section-lead"),
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
                            html.P("Search platform notifications across onboarding, BLs, Z-SADs, invoices, payments, cargo release, contracts, and support events.", className="muted section-lead"),
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
                                "All captured ZCAMS Chat questions and answers for quality review, classified as Good Response, Bad Response, or Neutral Response.",
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
                                    {"headerName": "Created", "field": "created_at", "width": 150, "pinned": "left"},
                                    {"headerName": "Company", "field": "company_name", "width": 190},
                                    {"headerName": "User", "field": "user_email", "width": 210},
                                    {"headerName": "Role", "field": "role", "width": 130},
                                    {
                                        "headerName": "Question",
                                        "field": "question",
                                        "width": 320,
                                        "minWidth": 280,
                                        "tooltipField": "question",
                                        "cellClass": "chat-question-cell",
                                    },
                                    {
                                        "headerName": "Answer",
                                        "field": "answer",
                                        "width": 560,
                                        "minWidth": 460,
                                        "tooltipField": "answer",
                                        "cellClass": "chat-answer-cell",
                                    },
                                    {"headerName": "Mode", "field": "mode", "width": 120},
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


def _bulk_register_cfas(records: list[dict]) -> dict:
    created = []
    resent = []
    skipped = []
    failed = []
    for index, record in enumerate(records, start=1):
        email = (record.get("email") or "").strip().lower()
        if not email:
            failed.append({"row": index, "email": "-", "reason": "Missing email"})
            continue
        try:
            existing = repository.row(
                """
                SELECT id, company_id, first_name, last_name, email, role
                FROM users
                WHERE lower(email) = lower(?)
                """,
                (email,),
            )
            if existing:
                if existing.get("role") != auth.ROLE_COMPANY_ADMIN:
                    repository.execute(
                        "UPDATE users SET role = ?, status = 'ACTIVE' WHERE id = ?",
                        (auth.ROLE_COMPANY_ADMIN, existing["id"]),
                    )
                mail_result = repository.email_new_user_registration(existing["id"], source="bulk-cfa")
                resent.append(
                    {
                        "company": record.get("company_name") or email,
                        "email": email,
                        "sent": bool(mail_result.get("email_result", {}).get("sent")),
                        "mode": mail_result.get("email_result", {}).get("mode") or "-",
                        "reason": mail_result.get("email_result", {}).get("reason") or "",
                        "role": auth.ROLE_COMPANY_ADMIN,
                    }
                )
                continue
            onboarding = repository.create_onboarding(
                {
                    "company_name": record.get("company_name"),
                    "pacra_number": record.get("pacra_number"),
                    "tpin": record.get("tpin"),
                    "zra_licence": record.get("zra_licence"),
                    "zaffa_number": record.get("zaffa_number"),
                    "company_email": record.get("company_email") or email,
                    "phone": record.get("phone"),
                    "whatsapp": record.get("whatsapp") or record.get("phone"),
                    "first_name": record.get("first_name"),
                    "last_name": record.get("last_name"),
                    "email": email,
                    "username": record.get("username") or email,
                    "password": repository.generate_temp_password(),
                }
            )
            approved = repository.approve_company(onboarding["company_id"], registration_source="bulk-cfa")
            email_result = approved.get("email", {})
            created.append(
                {
                    "company": approved.get("company", {}).get("name") or record.get("company_name"),
                    "email": email,
                    "sent": bool(email_result.get("sent")),
                    "mode": email_result.get("mode") or "-",
                    "reason": email_result.get("reason") or "",
                    "role": auth.ROLE_COMPANY_ADMIN,
                }
            )
        except ValueError as exc:
            failed.append({"row": index, "email": email, "reason": str(exc)})
        except Exception as exc:  # noqa: BLE001
            failed.append({"row": index, "email": email, "reason": str(exc)})
    return {"created": created, "resent": resent, "skipped": skipped, "failed": failed}


def _bulk_registration_notice(result: dict) -> html.Div:
    created = result.get("created") or []
    resent = result.get("resent") or []
    skipped = result.get("skipped") or []
    failed = result.get("failed") or []
    sent_count = sum(1 for item in [*created, *resent] if item.get("sent"))
    table_rows = []
    for item in created:
        table_rows.append({**item, "status": "Created", "tone": "success", "note": "CFA approved and Company Admin credentials generated."})
    for item in resent:
        table_rows.append({**item, "status": "Credentials reissued", "tone": "info", "note": "Existing account enforced as Company Admin and sent fresh credentials."})
    for item in skipped:
        table_rows.append({**item, "company": "-", "status": "Skipped", "tone": "warning", "sent": False, "mode": "-", "note": item.get("reason") or ""})
    for item in failed:
        table_rows.append({**item, "company": "-", "status": "Failed", "tone": "danger", "sent": False, "mode": "-", "note": item.get("reason") or ""})

    summary = html.Div(
        [
            html.Div([html.Strong(len(created)), html.Span("Created")], className="bulk-summary-card success"),
            html.Div([html.Strong(len(resent)), html.Span("Credentials reissued")], className="bulk-summary-card info"),
            html.Div([html.Strong(sent_count), html.Span("Credentials emailed")], className="bulk-summary-card mail"),
            html.Div([html.Strong(len(failed)), html.Span("Failed")], className="bulk-summary-card danger" if failed else "bulk-summary-card"),
        ],
        className="bulk-summary-grid",
    )
    table = html.Div(
        html.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th("CFA"),
                            html.Th("Admin Email"),
                            html.Th("Role"),
                            html.Th("Result"),
                            html.Th("Mail"),
                            html.Th("Notes"),
                        ]
                    )
                ),
                html.Tbody(
                    [
                        html.Tr(
                            [
                                html.Td(row.get("company") or "-"),
                                html.Td(row.get("email") or "-"),
                                html.Td(html.Span(row.get("role") or auth.ROLE_COMPANY_ADMIN, className="bulk-pill role")),
                                html.Td(html.Span(row.get("status"), className=f"bulk-pill {row.get('tone')}")),
                                html.Td(
                                    html.Span(
                                        "Sent" if row.get("sent") else "Not confirmed",
                                        className=f"bulk-pill {'success' if row.get('sent') else 'warning'}",
                                    )
                                ),
                                html.Td(row.get("note") or row.get("reason") or "-"),
                            ]
                        )
                        for row in table_rows
                    ]
                ),
            ],
            className="bulk-results-table",
        ),
        className="bulk-results-table-wrap",
    )
    status_class = "notice success bulk-result-card" if not failed else "notice error bulk-result-card"
    return html.Div([summary, table], className=status_class)


def _bulk_visibility_table(headers: list[str], rows_data: list[list]) -> html.Div:
    return html.Div(
        html.Table(
            [
                html.Thead(html.Tr([html.Th(header) for header in headers])),
                html.Tbody(
                    [html.Tr([html.Td(cell) for cell in row_data]) for row_data in rows_data]
                    if rows_data
                    else [html.Tr([html.Td("No tracked activity yet.", colSpan=len(headers), className="muted")])]
                ),
            ],
            className="bulk-visibility-table",
        ),
        className="bulk-visibility-table-wrap",
    )


def _ip_location_action(ip_address: str | None, button_id) -> html.Div:
    ip = (ip_address or "-").strip() or "-"
    return html.Div(
        [
            html.Span(ip),
            html.Button(
                icon("lucide:eye", 14),
                id=button_id,
                n_clicks=0,
                className="ip-eye-button",
                title=f"View login location for {ip}",
                type="button",
                **{"aria-label": f"View login location for {ip}"},
            ),
        ],
        className="ip-cell-action",
    )


def _bulk_visibility_panel() -> html.Div:
    data = repository.bulk_registration_visibility()
    summary = data["summary"]
    engagement_rows = [
        [
            item.get("company_name") or item.get("company_id") or "-",
            f"{item.get('first_name') or ''} {item.get('last_name') or ''}".strip() or item.get("email") or "-",
            item.get("email") or "-",
            str(item.get("link_clicks") or 0),
            (item.get("last_clicked_at") or "-")[:19],
            str(item.get("login_attempts") or 0),
            str(item.get("successful_logins") or 0),
            str(item.get("failed_logins") or 0),
            (item.get("last_login_attempt_at") or "-")[:19],
        ]
        for item in data["users"]
    ]
    click_rows = [
        [
            (item.get("created_at") or "-")[:19],
            item.get("company_name") or "-",
            item.get("user_email") or item.get("email") or "-",
            item.get("source") or "-",
            item.get("ip_address") or "-",
        ]
        for item in data["clicks"]
    ]
    login_rows = []
    for index, item in enumerate(data["logins"]):
        ip_address = item.get("ip_address") or "-"
        login_rows.append(
            [
                (item.get("created_at") or "-")[:19],
                item.get("company_name") or "-",
                item.get("user_email") or item.get("email") or "-",
                "Success" if int(item.get("success") or 0) else "Failed",
                item.get("failure_reason") or "-",
                _ip_location_action(
                    ip_address,
                    {
                        "type": "super-admin-bulk-login-location-open",
                        "ip": ip_address,
                        "index": index,
                    },
                ),
            ]
        )
    return html.Div(
        [
            html.Div(
                [
                    html.Div([icon("lucide:eye", 16), html.Strong("Registration Visibility & Login Analytics")], className="bulk-visibility-title"),
                    html.P(
                        "Tracks CFA admin credential-link visits and login attempts. New bulk emails include a tracked login link.",
                        className="muted",
                    ),
                ],
                className="stack compact",
            ),
            html.Div(
                [
                    html.Div([html.Strong(summary["company_admins"]), html.Span("Company admins")], className="bulk-summary-card info"),
                    html.Div([html.Strong(summary["clicked_users"]), html.Span("Clicked login link")], className="bulk-summary-card success"),
                    html.Div([html.Strong(summary["login_attempts"]), html.Span("Login attempts")], className="bulk-summary-card mail"),
                    html.Div([html.Strong(summary["failed_logins"]), html.Span("Failed logins")], className="bulk-summary-card danger" if summary["failed_logins"] else "bulk-summary-card"),
                ],
                className="bulk-summary-grid",
            ),
            html.Div(
                [
                    html.H4("CFA admin engagement"),
                    _bulk_visibility_table(
                        ["Company", "Admin", "Email", "Clicks", "Last click", "Attempts", "Success", "Failed", "Last attempt"],
                        engagement_rows,
                    ),
                    html.H4("Recent tracked link clicks"),
                    _bulk_visibility_table(["Time", "Company", "Email", "Source", "IP"], click_rows),
                    html.H4("Recent login attempts"),
                    _bulk_visibility_table(["Time", "Company", "Email", "Result", "Reason", "Location"], login_rows),
                ],
                className="bulk-visibility-sections",
            ),
        ],
        className="bulk-visibility-card",
    )


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
    Output("super-admin-bulk-file-preview", "children"),
    Output("super-admin-bulk-progress-fill", "style"),
    Output("super-admin-bulk-progress-text", "children"),
    Input("super-admin-bulk-cfa-upload", "filename"),
    Input("super-admin-bulk-cfa-upload", "contents"),
    prevent_initial_call=False,
)
def preview_bulk_cfa_upload(filename, contents):
    if not filename:
        return (
            html.Div([icon("lucide:file-search", 14), html.Span("No bulk registration file selected yet.")]),
            {"width": "0%"},
            "Waiting for upload.",
        )
    size_label = "File loaded and ready to process." if contents else "Waiting for file content."
    return (
        html.Div(
            [
                icon("lucide:file-check-2", 15),
                html.Strong(filename),
                html.Span(size_label),
            ]
        ),
        {"width": "35%"},
        f"Received {filename}. Processing will validate records and email Company Admin credentials.",
    )


@callback(
    Output("super-admin-bulk-visibility", "children"),
    Input("_pages_location", "pathname"),
    Input("super-admin-bulk-cfa-upload", "contents"),
    State("auth-user", "data"),
    prevent_initial_call=False,
)
def refresh_bulk_visibility(pathname, _contents, user):
    if pathname != "/super-admin":
        raise PreventUpdate
    if not user or user.get("role") != auth.ROLE_SUPER_ADMIN:
        raise PreventUpdate
    return _bulk_visibility_panel()


@callback(
    Output("super-admin-bulk-cfa-result", "children"),
    Output("super-admin-bulk-progress-fill", "style", allow_duplicate=True),
    Output("super-admin-bulk-progress-text", "children", allow_duplicate=True),
    Output("super-admin-company-picker", "options", allow_duplicate=True),
    Output("super-admin-companies-table", "rowData", allow_duplicate=True),
    Output("super-admin-user-picker", "options", allow_duplicate=True),
    Output("super-admin-users-grid", "rowData", allow_duplicate=True),
    Input("super-admin-bulk-cfa-upload", "contents"),
    State("super-admin-bulk-cfa-upload", "filename"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def bulk_auto_register_cfas(contents, filename, user):
    if not contents:
        raise PreventUpdate
    try:
        _require_super_admin(user)
        records = parse_bulk_registration_upload(filename or "bulk-cfas.csv", contents)
        result = _bulk_register_cfas(records)
        notice = _bulk_registration_notice(result)
        progress_style = {"width": "100%"}
        progress_text = f"Completed: {len(result.get('created') or [])} created, {len(result.get('resent') or [])} credentials reissued, {len(result.get('failed') or [])} failed."
    except Exception as exc:  # noqa: BLE001
        notice = html.Div(str(exc), className="notice error")
        progress_style = {"width": "100%", "background": "linear-gradient(90deg, #dc2626, #f97316)"}
        progress_text = "Bulk registration failed. Review the error message below."
    company_rows = _company_report_rows()
    user_rows = _user_report_rows()
    return (
        notice,
        progress_style,
        progress_text,
        _select_options(company_rows, ("name", "company_email", "status")),
        company_rows,
        _select_options(user_rows, ("name", "email", "role", "status")),
        user_rows,
    )


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
    Output("super-admin-login-visibility-modal", "className"),
    Output("super-admin-login-visibility-modal", "children"),
    Input("super-admin-login-visibility-open", "n_clicks"),
    Input("super-admin-login-visibility-close", "n_clicks"),
    State("super-admin-session-picker", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def toggle_login_visibility_modal(open_clicks, close_clicks, selected_session_id, user):
    from dash import ctx

    if ctx.triggered_id == "super-admin-login-visibility-close":
        return "modal-backdrop is-hidden", no_update
    if not open_clicks:
        raise PreventUpdate
    _require_super_admin(user)
    return "modal-backdrop login-visibility-backdrop", _login_visibility_modal(selected_session_id)


@callback(
    Output("super-admin-activity-ip-geo-modal", "className"),
    Output("super-admin-activity-ip-geo-modal", "children"),
    Input({"type": "super-admin-ip-geo-open", "ip": ALL, "index": ALL}, "n_clicks"),
    Input({"type": "super-admin-ip-geo-close", "ip": ALL}, "n_clicks"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def toggle_activity_ip_geo_modal(_open_clicks, _close_clicks, user):
    from dash import ctx

    trigger = ctx.triggered_id
    triggered_value = ctx.triggered[0].get("value") if ctx.triggered else None
    has_real_click = (
        any((click or 0) > 0 for click in triggered_value)
        if isinstance(triggered_value, list)
        else (triggered_value or 0) > 0
    )
    if not has_real_click:
        raise PreventUpdate
    if isinstance(trigger, dict) and trigger.get("type") == "super-admin-ip-geo-close":
        return "modal-backdrop is-hidden", []
    if not isinstance(trigger, dict) or trigger.get("type") != "super-admin-ip-geo-open":
        raise PreventUpdate
    _require_super_admin(user)
    ip_address = trigger.get("ip")
    return "modal-backdrop login-visibility-backdrop", _ip_geo_modal(ip_address, "super-admin-ip-geo-close")


@callback(
    Output("super-admin-bulk-ip-geo-modal", "className"),
    Output("super-admin-bulk-ip-geo-modal", "children"),
    Input({"type": "super-admin-bulk-login-location-open", "ip": ALL, "index": ALL}, "n_clicks"),
    Input({"type": "super-admin-bulk-ip-geo-close", "ip": ALL}, "n_clicks"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def toggle_bulk_ip_geo_modal(_open_clicks, _close_clicks, user):
    from dash import ctx

    trigger = ctx.triggered_id
    triggered_value = ctx.triggered[0].get("value") if ctx.triggered else None
    has_real_click = (
        any((click or 0) > 0 for click in triggered_value)
        if isinstance(triggered_value, list)
        else (triggered_value or 0) > 0
    )
    if not has_real_click:
        raise PreventUpdate
    if isinstance(trigger, dict) and trigger.get("type") == "super-admin-bulk-ip-geo-close":
        return "modal-backdrop is-hidden", []
    if not isinstance(trigger, dict) or trigger.get("type") != "super-admin-bulk-login-location-open":
        raise PreventUpdate
    _require_super_admin(user)
    ip_address = trigger.get("ip")
    return "modal-backdrop login-visibility-backdrop", _ip_geo_modal(ip_address, "super-admin-bulk-ip-geo-close")


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
    Input("super-admin-users-grid", "selectedRows"),
    prevent_initial_call=True,
)
def load_selected_super_admin_user(selected_user_id, selected_rows):
    selected_id = _selected_user_id_from_grid(
        selected_user_id,
        selected_rows,
        prefer_grid=ctx.triggered_id == "super-admin-users-grid",
    )
    row = repository.get_system_user(selected_id) if selected_id else {}
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
    Output("super-admin-resend-progress", "children"),
    Output("super-admin-user-picker", "options", allow_duplicate=True),
    Output("super-admin-users-grid", "rowData", allow_duplicate=True),
    Input("super-admin-update-user", "n_clicks"),
    Input("super-admin-suspend-user", "n_clicks"),
    Input("super-admin-activate-user", "n_clicks"),
    Input("super-admin-resend-user-email", "n_clicks"),
    Input("super-admin-delete-user", "n_clicks"),
    State("super-admin-user-picker", "value"),
    State("super-admin-users-grid", "selectedRows"),
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
    running=[
        (
            Output("super-admin-resend-progress-live", "children"),
            _mail_progress("Sending login credentials. Please wait...", 68, "sending"),
            _mail_progress(),
        )
    ],
)
def apply_super_admin_user_action(
    _update_clicks,
    _suspend_clicks,
    _activate_clicks,
    _resend_clicks,
    _delete_clicks,
    selected_id,
    selected_rows,
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
    trigger = ctx.triggered_id
    selected_id = _selected_user_id_from_grid(selected_id, selected_rows)
    if not selected_id:
        user_rows = _user_report_rows(search)
        return (
            html.Div("Select a user first.", className="notice error"),
            _mail_progress("Select one or more users before resending.", 0, "error"),
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
            progress = _mail_progress()
        elif trigger == "super-admin-suspend-user":
            updated = repository.set_system_user_status(selected_id, "SUSPENDED")
            notice = html.Div(f"Suspended {updated.get('email')}.", className="notice success")
            progress = _mail_progress()
        elif trigger == "super-admin-activate-user":
            updated = repository.set_system_user_status(selected_id, "ACTIVE")
            notice = html.Div(f"Activated {updated.get('email')}.", className="notice success")
            progress = _mail_progress()
        elif trigger == "super-admin-resend-user-email":
            target_ids = [row.get("id") for row in (selected_rows or []) if row.get("id")] or [selected_id]
            sent = []
            failed = []
            for target_id in target_ids:
                delivery = repository.resend_user_credentials(
                    target_id,
                    source="super-admin-resend",
                    actor_role=auth.ROLE_SUPER_ADMIN,
                )
                email_result = delivery.get("email_result") or {}
                user = delivery.get("user") or {}
                if email_result.get("sent"):
                    sent.append(user.get("email") or target_id)
                else:
                    failed.append(f"{user.get('email') or target_id}: temporary password {delivery.get('temp_password')}")
            if failed:
                notice = html.Div(
                    [
                        html.Strong(f"Credentials resent to {len(sent)} user(s). "),
                        html.Span("Some emails were not confirmed: "),
                        html.Span("; ".join(failed)),
                    ],
                    className="notice error",
                )
                progress = _mail_progress(f"Resend completed with {len(failed)} email issue(s).", 100, "error")
            else:
                notice = html.Div(f"Credentials resent to {len(sent)} user(s). Each user must set a new password on first login.", className="notice success")
                progress = _mail_progress(f"Mail sent to {len(sent)} user(s).", 100, "success")
        elif trigger == "super-admin-delete-user":
            repository.delete_system_user(selected_id)
            notice = html.Div("User deleted.", className="notice success")
            progress = _mail_progress()
        else:
            raise PreventUpdate
    except PreventUpdate:
        raise
    except Exception as exc:  # noqa: BLE001
        notice = html.Div(str(exc), className="notice error")
        progress = _mail_progress("Resend failed before mail could be sent.", 100, "error")
    user_rows = _user_report_rows(search)
    return notice, progress, _select_options(user_rows, ("name", "email", "role", "status")), user_rows


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
