import dash_ag_grid as dag
from dash import Input, Output, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate

from components.layout import header
from services import repository


register_page(__name__, path="/support", name="Support")


def layout(**_kwargs):
    return html.Div(
        [
            header(
                "Support",
                help_text="Report view for support tickets raised in ZCAMS.",
                pathname="/support",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H2("Support Report"),
                            html.P(
                                "Search support tickets by company, issue, module, priority, status, and creator. Super Admin and Admin Support see platform-wide tickets; company users see their own CFA tickets.",
                                className="muted section-lead",
                            ),
                            dcc.Input(
                                id="support-report-search",
                                placeholder="Search tickets by company, subject, module, priority, status...",
                                className="form-control report-search",
                            ),
                            dag.AgGrid(
                                id="support-report-grid",
                                columnDefs=[
                                    {"headerName": "Created", "field": "created_at", "width": 160},
                                    {"headerName": "Company", "field": "company_name", "width": 190},
                                    {"headerName": "Subject", "field": "subject", "flex": 1},
                                    {"headerName": "Description", "field": "description", "flex": 2},
                                    {"headerName": "Module", "field": "module", "width": 130},
                                    {"headerName": "Priority", "field": "priority", "width": 120},
                                    {"headerName": "Status", "field": "status", "width": 120},
                                    {"headerName": "Created By", "field": "created_by", "width": 190},
                                ],
                                rowData=[],
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
                                    "paginationPageSize": 12,
                                    "animateRows": True,
                                    "domLayout": "autoHeight",
                                },
                                rowClassRules={
                                    "ticket-open-row": "params.data.status === 'Open'",
                                    "ticket-resolved-row": "params.data.status === 'Resolved'",
                                },
                                className="ag-theme-alpine zcams-ag-grid",
                            ),
                        ],
                        className="card section-card stack",
                    ),
                ],
                className="page-content stack",
            ),
        ]
    )


def _ticket_rows(user: dict | None, search: str | None = None) -> list[dict]:
    role = (user or {}).get("role")
    company_id = None if role in {"SUPER_ADMIN", "ADMIN"} else (user or {}).get("company_id") or repository.DEMO_COMPANY_ID
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
        }
        for ticket in repository.list_support_tickets(company_id=company_id, search=search)
    ]


@callback(
    Output("support-report-grid", "rowData"),
    Input("support-report-search", "value"),
    Input("auth-user", "data"),
    Input("_pages_location", "pathname"),
    prevent_initial_call=False,
)
def render_support_report(search, user, pathname):
    if (pathname or "") != "/support":
        raise PreventUpdate
    return _ticket_rows(user, search)
