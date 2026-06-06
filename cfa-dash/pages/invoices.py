from dash import ALL, Input, Output, State, callback, clientside_callback, ctx, dcc, html, register_page
from dash.exceptions import PreventUpdate

from components.icons import icon
from components.layout import header
from components.ui import badge, status_table
from components.workflow import shortcut_chip
from services import repository


register_page(__name__, path="/invoices", name="Invoices")


def layout(**_kwargs):
    outstanding = 0
    return html.Div(
        [
            dcc.Store(id="invoice-filter-mode", data="all"),
            dcc.Store(id="invoice-copy-status"),
            header(
                "Invoices",
                actions=[
                    dcc.Link([icon("lucide:file-check-2", 14), "Create from Reviewed BL"], href="/reviewed-bl#active-reviewed-bls", className="btn-primary compact-header-action"),
                    dcc.Link([icon("lucide:credit-card", 14), "Check-out"], href="/checkout", className="btn-secondary"),
                ],
                help_text="Invoices are generated from Reviewed BLs. ZCAMS enforces GN 83, signs invoices through CapitalPay, and tracks payment status.",
                pathname="/invoices",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            shortcut_chip("Request new invoice", "/reviewed-bl#active-reviewed-bls", "lucide:receipt", "primary"),
                            shortcut_chip("Share payment links", "/checkout", "lucide:credit-card"),
                        ],
                        className="shortcut-row",
                    ),
                    html.Div(
                        [
                            html.Button("All", id="invoice-filter-all", className="filter-tab active"),
                            html.Button("Outstanding", id="invoice-filter-outstanding", className="filter-tab"),
                            html.Button("Settled", id="invoice-filter-settled", className="filter-tab"),
                        ],
                        className="filter-tabs",
                    ),
                    html.Div(id="invoice-action-result"),
                    html.Div(
                        [
                            html.H2("Invoice Register"),
                            html.P(
                                "Track GN 83 invoices, CapitalPay numbers, payment links, PDF actions, WhatsApp sharing, and settlement state.",
                                className="muted section-lead",
                            ),
                            dcc.Input(
                                id="invoice-search",
                                className="form-control invoice-register-search",
                                placeholder="Search by Invoice or CapitalPay No",
                                debounce=True,
                            ),
                            html.Div(
                                id="invoice-table",
                                children=html.P("Loading invoices…", className="muted"),
                            ),
                        ],
                        className="card section-card",
                    ),
                ],
                className="page-content stack",
            ),
        ]
    )


def _invoice_table(invoices, filter_mode: str = "all", search_value: str | None = None):
    filtered = invoices
    if filter_mode == "outstanding":
        filtered = [inv for inv in invoices if inv["status"] != "SETTLED"]
    elif filter_mode == "settled":
        filtered = [inv for inv in invoices if inv["status"] == "SETTLED"]
    query = str(search_value or "").strip().lower()
    if query:
        filtered = [
            inv
            for inv in filtered
            if query in str(inv.get("invoice_number") or "").lower()
            or query in repository.invoice_capitalpay_number(inv).lower()
        ]
    return status_table(
        ["Invoice", "CapitalPay No", "Payment Link", "BL", "Z-SAD", "Type", "Amount Due", "Status", "PDF", "Share", "Action"],
        [
            [
                inv["invoice_number"],
                repository.invoice_capitalpay_number(inv),
                _payment_link_cell(inv),
                inv["bl_number"],
                inv["z_sad_number"],
                inv["invoice_type"].replace("_", " ").title(),
                repository.money(repository.invoice_gn83_total(inv)),
                badge(inv["status"]),
                html.A(
                    icon("lucide:file-down", 16),
                    href=repository.invoice_download_url(inv["id"]),
                    target="_blank",
                    className="invoice-icon-action invoice-icon-action--pdf",
                    title="Download signed invoice PDF",
                ),
                html.A(
                    icon("lucide:message-circle", 16),
                    href=repository.invoice_whatsapp_link(inv["id"]),
                    target="_blank",
                    className="invoice-icon-action invoice-icon-action--whatsapp",
                    title="Share invoice via WhatsApp",
                ),
                html.Button(
                    icon("lucide:check-circle-2", 16),
                    id={"type": "settle-invoice", "id": inv["id"]},
                    className="invoice-icon-action invoice-icon-action--settle",
                    disabled=inv["status"] == "SETTLED",
                    title="Mark settled",
                ),
            ]
            for inv in filtered
        ],
    )


def _payment_link_cell(invoice: dict):
    checkout_url = f"/capitalpay/checkout/{invoice['id']}"
    return html.Div(
        [
            html.A(
                icon("lucide:external-link", 15),
                href=checkout_url,
                target="_blank",
                className="invoice-icon-action invoice-icon-action--open",
                title="Open CapitalPay checkout",
            ),
            html.Button(
                icon("lucide:copy", 15),
                id={"type": "copy-payment-link", "id": invoice["id"]},
                value=checkout_url,
                className="invoice-icon-action invoice-icon-action--copy",
                title="Copy CapitalPay checkout link",
            ),
        ],
        className="invoice-link-actions",
    )


@callback(
    Output("invoice-filter-outstanding", "children"),
    Input("_pages_location", "pathname"),
    Input("auth-user", "data"),
    prevent_initial_call=False,
)
def update_outstanding_tab(pathname, user):
    if (pathname or "") != "/invoices":
        raise PreventUpdate
    invoices = repository.list_invoices_for_user(user)
    outstanding = sum(1 for inv in invoices if inv["status"] != "SETTLED")
    return f"Outstanding ({outstanding})"


def _filter_tab_classes(mode: str):
    base = "filter-tab"
    active = f"{base} active"
    return (
        active if mode == "all" else base,
        active if mode == "outstanding" else base,
        active if mode == "settled" else base,
    )


@callback(
    Output("invoice-filter-mode", "data"),
    Output("invoice-filter-all", "className"),
    Output("invoice-filter-outstanding", "className"),
    Output("invoice-filter-settled", "className"),
    Output("invoice-table", "children"),
    Output("invoice-action-result", "children"),
    Input("_pages_location", "pathname"),
    Input("invoice-filter-all", "n_clicks"),
    Input("invoice-filter-outstanding", "n_clicks"),
    Input("invoice-filter-settled", "n_clicks"),
    Input("invoice-search", "value"),
    Input("auth-user", "data"),
    State("invoice-filter-mode", "data"),
    prevent_initial_call=False,
)
def filter_invoices(pathname, _all, _out, _settled, search_value, user, current_mode):
    if (pathname or "") != "/invoices":
        raise PreventUpdate

    trigger = ctx.triggered_id
    mode = current_mode or "all"
    if trigger == "invoice-filter-outstanding":
        mode = "outstanding"
    elif trigger == "invoice-filter-settled":
        mode = "settled"
    elif trigger == "invoice-filter-all":
        mode = "all"
    invoices = repository.list_invoices_for_user(user)
    return mode, *_filter_tab_classes(mode), _invoice_table(invoices, mode, search_value), None


@callback(
    Output("invoice-action-result", "children", allow_duplicate=True),
    Output("invoice-filter-mode", "data", allow_duplicate=True),
    Output("invoice-filter-all", "className", allow_duplicate=True),
    Output("invoice-filter-outstanding", "className", allow_duplicate=True),
    Output("invoice-filter-settled", "className", allow_duplicate=True),
    Output("invoice-table", "children", allow_duplicate=True),
    Input({"type": "settle-invoice", "id": ALL}, "n_clicks"),
    State("invoice-filter-mode", "data"),
    State("invoice-search", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def settle_invoice(_clicks, filter_mode, search_value, user):
    from dash import ctx, no_update

    trigger = ctx.triggered_id
    if not isinstance(trigger, dict):
        return (no_update,) * 6
    invoice = repository.settle_invoice(trigger["id"])
    mode = filter_mode or "all"
    invoices = repository.list_invoices_for_user(user)
    notice = html.Div(
        [
            html.Div(f"Invoice {invoice['invoice_number']} marked settled.", className="notice success"),
            dcc.Link("Issue cargo release on Reviewed BL", href="/reviewed-bl#active-reviewed-bls", className="btn-secondary"),
        ],
        className="stack compact",
    )
    return notice, mode, *_filter_tab_classes(mode), _invoice_table(invoices, mode, search_value)


clientside_callback(
    """
    function(clicks, values) {
        const triggered = dash_clientside.callback_context.triggered;
        if (!triggered || !triggered.length) {
            return '';
        }
        const rawId = triggered[0].prop_id.split('.')[0];
        let index = -1;
        try {
            const id = JSON.parse(rawId);
            const ids = dash_clientside.callback_context.inputs_list[0].map(item => item.id.id);
            index = ids.indexOf(id.id);
        } catch (e) {
            return '';
        }
        const url = values && index >= 0 ? values[index] : '';
        if (!url || !navigator.clipboard) {
            return '';
        }
        const absoluteUrl = new URL(url, window.location.origin).href;
        navigator.clipboard.writeText(absoluteUrl);
        return absoluteUrl;
    }
    """,
    Output("invoice-copy-status", "data"),
    Input({"type": "copy-payment-link", "id": ALL}, "n_clicks"),
    State({"type": "copy-payment-link", "id": ALL}, "value"),
    prevent_initial_call=True,
)
