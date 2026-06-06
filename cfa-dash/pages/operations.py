from __future__ import annotations

from dash import ALL, Input, Output, State, callback, dash_table, dcc, html, register_page
from dash.exceptions import PreventUpdate

from components.icons import icon
from components.layout import header, section_label
from services import auth
from services import settlement_repository as settlements


register_page(__name__, path="/operations", name="Operations")


STATUS_FILTERS = settlements.STATUS_FILTERS


def layout(**_kwargs):
    return html.Div(
        [
            dcc.Store(id="operations-settlement-run"),
            dcc.Store(id="operations-download-modal-state"),
            dcc.Download(id="operations-settlement-download"),
            header(
                "Operations Settlement Dashboard",
                actions=[
                    html.Button(
                        [icon("lucide:refresh-cw", 14), "Refresh Analytics"],
                        id="operations-refresh",
                        className="btn-secondary",
                        type="button",
                    ),
                ],
                help_text=(
                    "Operations dashboard for T-CAMS invoicing and settlement analytics. "
                    "Review the compiled settlement run, then download the bank XML file."
                ),
                pathname="/operations",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span(icon("lucide:landmark", 22), className="operations-hero-icon"),
                                    html.Div(
                                        [
                                            html.H2("T-CAMS Invoicing & Settlement Analytics"),
                                            html.P(
                                                "Live settlement run compiled from invoice/payment records, CFA bank details, and CapitalPay references.",
                                                className="muted",
                                            ),
                                        ]
                                    ),
                                ],
                                className="operations-title-row",
                            ),
                            html.Div(id="operations-summary"),
                        ],
                        className="card section-card operations-hero-card",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2("CFA Settlement Table"),
                                    html.P(
                                        "One row per CFA beneficiary. Missing bank details, failed payments, and discrepancies are flagged before export.",
                                        className="muted section-lead",
                                    ),
                                ],
                                className="stack compact",
                            ),
                            html.Div(
                                [
                                    dcc.Input(
                                        id="operations-settlement-search",
                                        className="form-control operations-search",
                                        placeholder="Search CFA, licence, bank, or CapitalPay reference",
                                        debounce=False,
                                    ),
                                    dcc.Dropdown(
                                        id="operations-status-filter",
                                        options=[{"label": status, "value": status} for status in STATUS_FILTERS],
                                        value="All Transactions",
                                        clearable=False,
                                        className="operations-status-dropdown",
                                    ),
                                ],
                                className="operations-toolbar",
                            ),
                            html.Div(id="operations-status-tabs"),
                            section_label(
                                "Settlement Beneficiaries",
                                "Review each CFA beneficiary, bank readiness, settlement amount, CapitalPay evidence, and export status before download.",
                                "lucide:table-properties",
                            ),
                            html.Div(id="operations-settlement-table"),
                            html.Div(
                                [
                                    dcc.Checklist(
                                        id="operations-review-confirmed",
                                        options=[
                                            {
                                                "label": "Operations has reviewed the settlement list and flags.",
                                                "value": "reviewed",
                                            }
                                        ],
                                        value=[],
                                        className="operations-review-check",
                                    ),
                                    html.Button(
                                        [icon("lucide:file-down", 15), "Download Settlement Report"],
                                        id="operations-open-download-confirm",
                                        className="btn-primary",
                                        type="button",
                                        disabled=True,
                                    ),
                                ],
                                className="operations-download-row",
                            ),
                            html.Div(id="operations-download-feedback"),
                        ],
                        className="card section-card operations-table-card",
                    ),
                    html.Div(
                        [
                            html.H2("Download Audit Log"),
                            html.P(
                                "Every settlement XML download is logged with user, time, file, CFA count, and run total.",
                                className="muted section-lead",
                            ),
                            html.Div(id="operations-download-log"),
                        ],
                        className="card section-card operations-log-card",
                    ),
                ],
                className="page-content stack operations-page",
            ),
            html.Div(id="operations-download-modal", className="modal-backdrop is-hidden"),
        ]
    )


def _require_operations_access(user: dict | None) -> None:
    role = auth.normalize_role((user or {}).get("role"))
    if role not in {auth.ROLE_SUPER_ADMIN, auth.ROLE_OPERATIONS}:
        raise PreventUpdate


def _money_tzs(value) -> str:
    return f"TZS {float(value or 0):,.2f}"


def _summary_cards(data: dict) -> html.Div:
    run = data["run"]
    summary = data["summary"]
    return html.Div(
        [
            html.Div([html.Strong(_money_tzs(summary["total_amount_tzs"])), html.Span("Total to settle")], className="operations-kpi-card amount"),
            html.Div([html.Strong(str(summary["cfa_count"])), html.Span("CFAs to pay")], className="operations-kpi-card companies"),
            html.Div([html.Strong((run.get("prepared_at") or "-")[:19]), html.Span("Last analytics run")], className="operations-kpi-card run"),
            html.Div([html.Strong(str(summary["flagged_count"])), html.Span("Flags for review")], className="operations-kpi-card flags" if summary["flagged_count"] else "operations-kpi-card"),
            html.Div([html.Strong(run.get("run_number") or "-"), html.Span("Current run")], className="operations-kpi-card runno"),
        ],
        className="operations-kpi-grid",
    )


def _status_tabs(data: dict, selected_status: str) -> html.Div:
    counts = data["summary"]["status_counts"]
    total = data["summary"]["cfa_count"]
    buttons = []
    for status in STATUS_FILTERS:
        count = total if status == "All Transactions" else counts.get(status, 0)
        buttons.append(
            html.Button(
                f"{status} ({count})",
                id={"type": "operations-status-tab", "status": status},
                className="filter-tab active" if status == selected_status else "filter-tab",
                type="button",
            )
        )
    return html.Div(buttons, className="filter-tabs operations-filter-tabs")


def _settlement_table(items: list[dict]) -> html.Div:
    columns = [
        {"name": "CFA Company Name", "id": "cfa_company_name"},
        {"name": "CFA Licence Number", "id": "cfa_licence_number"},
        {"name": "Bank Name", "id": "bank_name"},
        {"name": "Bank Account Number", "id": "bank_account_number"},
        {"name": "Bank Branch", "id": "bank_branch"},
        {"name": "Amount Owed (TZS)", "id": "amount_tzs", "type": "numeric"},
        {"name": "Declarations", "id": "declarations_count", "type": "numeric"},
        {"name": "Payment Status", "id": "payment_status"},
        {"name": "Last Updated", "id": "last_updated_at"},
        {"name": "Flag", "id": "flag_display"},
    ]
    table_rows = []
    tooltips = []
    for item in items:
        flag_reason = item.get("flag_reason") or ""
        table_rows.append(
            {
                "cfa_company_name": item.get("cfa_company_name") or "-",
                "cfa_licence_number": item.get("cfa_licence_number") or "-",
                "bank_name": item.get("bank_name") or "-",
                "bank_account_number": item.get("bank_account_number") or "-",
                "bank_branch": item.get("bank_branch") or "-",
                "amount_tzs": round(float(item.get("amount_tzs") or 0), 2),
                "declarations_count": int(item.get("declarations_count") or 0),
                "payment_status": item.get("payment_status") or "Pending",
                "last_updated_at": (item.get("last_updated_at") or "-")[:19],
                "flag_display": f"FLAG: {flag_reason}" if flag_reason else "Ready",
            }
        )
        tooltips.append(
            {
                "flag_display": {"value": flag_reason or "No flag for this CFA.", "type": "markdown"},
                "amount_tzs": {"value": _money_tzs(item.get("amount_tzs")), "type": "markdown"},
            }
        )
    return html.Div(
        dash_table.DataTable(
            columns=columns,
            data=table_rows,
            tooltip_data=tooltips,
            sort_action="native",
            page_action="native",
            page_size=12,
            fixed_rows={"headers": True},
            style_table={"overflowX": "auto", "minWidth": "100%"},
            style_cell={
                "fontFamily": "Inter, system-ui, sans-serif",
                "fontSize": "13px",
                "padding": "11px 12px",
                "whiteSpace": "normal",
                "height": "auto",
                "textAlign": "left",
                "border": "0",
                "borderBottom": "1px solid rgba(207, 229, 199, 0.72)",
            },
            style_header={
                "backgroundColor": "#f5fbf3",
                "color": "#2f402b",
                "fontWeight": "800",
                "borderBottom": "1px solid rgba(207, 229, 199, 0.9)",
            },
            style_data_conditional=[
                {"if": {"column_id": "amount_tzs"}, "textAlign": "right", "fontVariantNumeric": "tabular-nums"},
                {"if": {"column_id": "declarations_count"}, "textAlign": "right", "fontVariantNumeric": "tabular-nums"},
                {"if": {"filter_query": "{flag_display} contains 'FLAG'"}, "backgroundColor": "rgba(254, 226, 226, 0.45)"},
                {"if": {"filter_query": "{payment_status} = 'Settled'", "column_id": "payment_status"}, "color": "#166534", "fontWeight": "800"},
                {"if": {"filter_query": "{payment_status} = 'Failed'", "column_id": "payment_status"}, "color": "#991b1b", "fontWeight": "800"},
                {"if": {"filter_query": "{payment_status} = 'Pending'", "column_id": "payment_status"}, "color": "#92400e", "fontWeight": "800"},
                {"if": {"filter_query": "{payment_status} = 'In-Progress'", "column_id": "payment_status"}, "color": "#1d4ed8", "fontWeight": "800"},
                {"if": {"filter_query": "{flag_display} contains 'FLAG'", "column_id": "flag_display"}, "color": "#991b1b", "fontWeight": "800"},
                {"if": {"filter_query": "{flag_display} = 'Ready'", "column_id": "flag_display"}, "color": "#166534", "fontWeight": "800"},
            ],
        ),
        className="operations-datatable-wrap",
    )


def _download_log(logs: list[dict]) -> html.Div:
    headers = ["Downloaded At", "User", "File", "CFAs", "Total Amount"]
    rows = [
        html.Tr(
            [
                html.Td((log.get("downloaded_at") or "-")[:19]),
                html.Td(log.get("user_email") or "-"),
                html.Td(log.get("file_name") or "-"),
                html.Td(str(log.get("cfa_count") or 0), className="numeric"),
                html.Td(_money_tzs(log.get("total_amount_tzs")), className="numeric"),
            ]
        )
        for log in logs
    ]
    return html.Div(
        html.Table(
            [
                html.Thead(html.Tr([html.Th(header) for header in headers])),
                html.Tbody(rows or [html.Tr(html.Td("No settlement downloads logged yet.", colSpan=len(headers), className="muted"))]),
            ],
            className="operations-settlement-table operations-log-table",
        ),
        className="operations-table-wrap",
    )


def _download_modal(run: dict, summary: dict) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(icon("lucide:file-down", 18), className="login-visibility-icon"),
                            html.Div(
                                [
                                    html.H2("Confirm Settlement Download"),
                                    html.P(
                                        f"You are about to download a settlement file for {summary['cfa_count']} CFAs "
                                        f"totalling {_money_tzs(summary['total_amount_tzs'])}. Confirm?",
                                        className="muted",
                                    ),
                                ]
                            ),
                        ],
                        className="modal-title-row",
                    ),
                    html.Button("x", id="operations-close-download-confirm", className="modal-close", type="button"),
                ],
                className="modal-header",
            ),
            html.Div(
                [
                    html.Div([html.Span("Settlement run"), html.Strong(run.get("run_number") or "-")], className="operations-confirm-detail"),
                    html.Div([html.Span("Prepared at"), html.Strong((run.get("prepared_at") or "-")[:19])], className="operations-confirm-detail"),
                    html.Div([html.Span("Output format"), html.Strong("XML")], className="operations-confirm-detail"),
                ],
                className="operations-confirm-grid",
            ),
            html.Div(
                [
                    html.Button("Cancel", id="operations-cancel-download", className="btn-secondary", type="button"),
                    html.Button(
                        [icon("lucide:check", 14), "Confirm & Download XML"],
                        id="operations-confirm-download",
                        className="btn-primary",
                        type="button",
                    ),
                ],
                className="row-actions",
            ),
        ],
        className="invoice-modal-card login-visibility-modal-card operations-confirm-modal",
    )


@callback(
    Output("operations-summary", "children"),
    Output("operations-status-tabs", "children"),
    Output("operations-settlement-table", "children"),
    Output("operations-download-log", "children"),
    Output("operations-settlement-run", "data"),
    Input("_pages_location", "pathname"),
    Input("operations-refresh", "n_clicks"),
    Input("operations-status-filter", "value"),
    Input("operations-settlement-search", "value"),
    State("auth-user", "data"),
    prevent_initial_call=False,
)
def render_operations_dashboard(pathname, _refresh_clicks, status_filter, search, user):
    if (pathname or "") != "/operations":
        raise PreventUpdate
    _require_operations_access(user)
    selected_status = status_filter or "All Transactions"
    data = settlements.settlement_dashboard_data(selected_status, search)
    return (
        _summary_cards(data),
        _status_tabs(data, selected_status),
        _settlement_table(data["items"]),
        _download_log(data["logs"]),
        data["run"],
    )


@callback(
    Output("operations-status-filter", "value"),
    Input({"type": "operations-status-tab", "status": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def apply_operations_status_tab(_clicks):
    from dash import ctx

    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or trigger.get("status") not in STATUS_FILTERS:
        raise PreventUpdate
    return trigger["status"]


@callback(
    Output("operations-open-download-confirm", "disabled"),
    Input("operations-review-confirmed", "value"),
    prevent_initial_call=False,
)
def toggle_operations_download_button(review_values):
    return "reviewed" not in (review_values or [])


@callback(
    Output("operations-download-modal", "className"),
    Output("operations-download-modal", "children"),
    Input("operations-open-download-confirm", "n_clicks"),
    Input("operations-close-download-confirm", "n_clicks"),
    Input("operations-cancel-download", "n_clicks"),
    State("operations-settlement-run", "data"),
    State("operations-status-filter", "value"),
    State("operations-settlement-search", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def toggle_operations_download_modal(_open_clicks, _close_clicks, _cancel_clicks, run, status_filter, search, user):
    from dash import ctx

    if ctx.triggered_id in {"operations-close-download-confirm", "operations-cancel-download"}:
        return "modal-backdrop is-hidden", []
    if ctx.triggered_id != "operations-open-download-confirm":
        raise PreventUpdate
    _require_operations_access(user)
    data = settlements.settlement_dashboard_data(status_filter or "All Transactions", search)
    return "modal-backdrop login-visibility-backdrop", _download_modal(run or data["run"], data["summary"])


@callback(
    Output("operations-settlement-download", "data"),
    Output("operations-download-feedback", "children"),
    Output("operations-download-log", "children", allow_duplicate=True),
    Output("operations-download-modal", "className", allow_duplicate=True),
    Output("operations-download-modal", "children", allow_duplicate=True),
    Input("operations-confirm-download", "n_clicks"),
    State("operations-settlement-run", "data"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def download_operations_settlement(_clicks, run, user):
    _require_operations_access(user)
    if not run or not run.get("id"):
        raise PreventUpdate
    file_name, xml_content, items, refreshed_run = settlements.build_settlement_xml(run["id"])
    total_amount = round(sum(float(item.get("amount_tzs") or 0) for item in items), 2)
    settlements.log_settlement_download(refreshed_run["id"], user, file_name, len(items), total_amount)
    dashboard_data = settlements.settlement_dashboard_data()
    feedback = html.Div(
        f"Settlement XML downloaded and logged: {file_name}",
        className="notice success",
    )
    return (
        {"content": xml_content, "filename": file_name, "type": "application/xml"},
        feedback,
        _download_log(dashboard_data["logs"]),
        "modal-backdrop is-hidden",
        [],
    )
