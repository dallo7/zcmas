from dash import ALL, Input, Output, State, callback, clientside_callback, ctx, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate

from components.icons import icon
from components.layout import header
from components.ui import badge, status_table
from components.workflow import shortcut_chip
from services import repository
from services.invoice_register import (
    INVOICE_PAGE_SIZE,
    filter_invoice_rows,
    invoice_register_counts,
    paginate_invoice_rows,
)


register_page(__name__, path="/invoices", name="Invoices")


def layout(**_kwargs):
    return html.Div(
        [
            dcc.Store(id="invoice-filter-mode", data="all"),
            dcc.Store(id="invoice-page", data=1),
            dcc.Store(id="invoice-presentation-mode", data=False),
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
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2("Invoice Register"),
                                            html.P(
                                                "Track GN 83 invoices, CapitalPay numbers, payment links, PDF actions, WhatsApp sharing, and settlement state.",
                                                className="muted section-lead",
                                            ),
                                        ],
                                        className="invoice-register-heading",
                                    ),
                                    html.Button(
                                        [icon("lucide:monitor", 16), "Presentation mode"],
                                        id="invoice-presentation-toggle",
                                        className="btn-secondary compact invoice-presentation-toggle",
                                        type="button",
                                        title="Larger text for projectors and low-resolution screens",
                                    ),
                                ],
                                className="invoice-register-toolbar",
                            ),
                            dcc.Input(
                                id="invoice-search",
                                className="form-control invoice-register-search",
                                placeholder="Search by Invoice, CapitalPay No, BL, or Z-SAD",
                                debounce=True,
                            ),
                            html.P(id="invoice-register-summary", className="table-filter-status muted"),
                            html.Div(
                                id="invoice-table-wrap",
                                children=html.P("Loading invoices…", className="muted"),
                            ),
                            html.Div(
                                [
                                    html.Button("Previous", id="invoice-page-prev", className="btn-secondary compact", type="button", disabled=True),
                                    html.Span(id="invoice-page-status", className="muted"),
                                    html.Button("Next", id="invoice-page-next", className="btn-secondary compact", type="button", disabled=True),
                                ],
                                id="invoice-pagination",
                                className="table-pagination",
                            ),
                        ],
                        id="invoice-register-card",
                        className="card section-card invoice-register-card",
                    ),
                ],
                className="page-content stack",
            ),
        ]
    )


def _invoice_action_button(label: str, *, icon_name: str, class_suffix: str, **kwargs):
    return html.Button(
        [icon(icon_name, 16), html.Span(label, className="invoice-action-label")],
        className=f"invoice-action-btn invoice-action-btn--{class_suffix}",
        type="button",
        **kwargs,
    )


def _invoice_action_link(label: str, *, icon_name: str, class_suffix: str, href: str, title: str):
    return html.A(
        [icon(icon_name, 16), html.Span(label, className="invoice-action-label")],
        href=href,
        target="_blank",
        className=f"invoice-action-btn invoice-action-btn--{class_suffix}",
        title=title,
    )


def _payment_link_cell(invoice: dict):
    checkout_url = f"/capitalpay/checkout/{invoice['id']}"
    return html.Div(
        [
            _invoice_action_link("Open", icon_name="lucide:external-link", class_suffix="open", href=checkout_url, title="Open CapitalPay checkout"),
            _invoice_action_button(
                "Copy",
                icon_name="lucide:copy",
                class_suffix="copy",
                id={"type": "copy-payment-link", "id": invoice["id"]},
                value=checkout_url,
                title="Copy CapitalPay checkout link",
            ),
        ],
        className="invoice-link-actions",
    )


def _invoice_table_rows(invoices: list[dict], *, company_whatsapp: dict[str, str]) -> list[list]:
    rows: list[list] = []
    for inv in invoices:
        company_id = inv.get("company_id") or repository.DEMO_COMPANY_ID
        fallback_phone = company_whatsapp.get(company_id)
        rows.append(
            [
                html.Span(inv["invoice_number"], className="invoice-register-primary"),
                html.Span(repository.invoice_capitalpay_number(inv), className="invoice-register-mono"),
                _payment_link_cell(inv),
                inv["bl_number"],
                html.Span(inv["z_sad_number"], className="invoice-register-mono"),
                inv["invoice_type"].replace("_", " ").title(),
                html.Strong(repository.money(repository.invoice_gn83_total(inv)), className="invoice-register-amount"),
                badge(inv["status"]),
                _invoice_action_link(
                    "PDF",
                    icon_name="lucide:file-down",
                    class_suffix="pdf",
                    href=repository.invoice_download_url(inv["id"]),
                    title="Download signed invoice PDF",
                ),
                _invoice_action_link(
                    "Share",
                    icon_name="lucide:message-circle",
                    class_suffix="whatsapp",
                    href=repository.invoice_whatsapp_link_from_invoice(inv, phone=fallback_phone),
                    title="Share invoice via WhatsApp",
                ),
                _invoice_action_button(
                    "Settle",
                    icon_name="lucide:check-circle-2",
                    class_suffix="settle",
                    id={"type": "settle-invoice", "id": inv["id"]},
                    disabled=inv["status"] == "SETTLED",
                    title="Mark settled",
                ),
            ]
        )
    return rows


def _company_whatsapp_cache(invoices: list[dict]) -> dict[str, str]:
    cache: dict[str, str] = {}
    for inv in invoices:
        company_id = inv.get("company_id") or repository.DEMO_COMPANY_ID
        if company_id in cache:
            continue
        company = repository.get_company(company_id)
        cache[company_id] = company.get("whatsapp") or company.get("phone") or ""
    return cache


def _invoice_register_table(page_rows: list[dict], *, presentation: bool) -> html.Div:
    table_class = "data-table invoice-register-table"
    if presentation:
        table_class += " is-presentation"
    if not page_rows:
        body = html.P("No invoices match this filter.", className="muted")
        return html.Div(body, className="invoice-register-table-scroll")
    table = status_table(
        ["Invoice", "CapitalPay No", "Payment", "BL", "Z-SAD", "Type", "Amount Due", "Status", "PDF", "Share", "Settle"],
        _invoice_table_rows(page_rows, company_whatsapp=_company_whatsapp_cache(page_rows)),
        table_class=table_class,
    )
    return html.Div(table, className="invoice-register-table-scroll")


def _filter_tab_classes(mode: str):
    base = "filter-tab"
    active = f"{base} active"
    return (
        active if mode == "all" else base,
        active if mode == "outstanding" else base,
        active if mode == "settled" else base,
    )


def _render_invoice_register(
    user,
    *,
    mode: str,
    search_value: str | None,
    page: int | None,
    presentation: bool,
    action_result=None,
):
    invoices = repository.list_invoices_for_user(user)
    total, outstanding, settled = invoice_register_counts(invoices)
    filtered = filter_invoice_rows(invoices, mode, search_value)
    page_rows, current_page, total_pages = paginate_invoice_rows(filtered, page)
    prev_disabled = current_page <= 1
    next_disabled = current_page >= total_pages or not filtered
    summary = (
        f"Showing {len(page_rows)} of {len(filtered)} filtered invoices "
        f"({total} total · {outstanding} outstanding · {settled} settled)"
    )
    card_class = "card section-card invoice-register-card"
    if presentation:
        card_class += " is-presentation"
    table = _invoice_register_table(page_rows, presentation=presentation)
    return (
        mode,
        current_page,
        presentation,
        *_filter_tab_classes(mode),
        f"Outstanding ({outstanding})",
        summary,
        table,
        f"Page {current_page} of {total_pages}",
        prev_disabled,
        next_disabled,
        card_class,
        action_result,
    )


@callback(
    Output("invoice-filter-mode", "data"),
    Output("invoice-page", "data"),
    Output("invoice-presentation-mode", "data"),
    Output("invoice-filter-all", "className"),
    Output("invoice-filter-outstanding", "className"),
    Output("invoice-filter-settled", "className"),
    Output("invoice-filter-outstanding", "children"),
    Output("invoice-register-summary", "children"),
    Output("invoice-table-wrap", "children"),
    Output("invoice-page-status", "children"),
    Output("invoice-page-prev", "disabled"),
    Output("invoice-page-next", "disabled"),
    Output("invoice-register-card", "className"),
    Output("invoice-action-result", "children"),
    Input("_pages_location", "pathname"),
    Input("invoice-filter-all", "n_clicks"),
    Input("invoice-filter-outstanding", "n_clicks"),
    Input("invoice-filter-settled", "n_clicks"),
    Input("invoice-search", "value"),
    Input("invoice-page-prev", "n_clicks"),
    Input("invoice-page-next", "n_clicks"),
    Input("invoice-presentation-toggle", "n_clicks"),
    Input("auth-user", "data"),
    State("invoice-filter-mode", "data"),
    State("invoice-page", "data"),
    State("invoice-presentation-mode", "data"),
    prevent_initial_call=False,
)
def refresh_invoice_register(
    pathname,
    _all,
    _out,
    _settled,
    search_value,
    _prev,
    _next,
    _presentation_click,
    user,
    current_mode,
    current_page,
    presentation_mode,
):
    if (pathname or "") != "/invoices":
        raise PreventUpdate

    trigger = ctx.triggered_id
    mode = current_mode or "all"
    page = int(current_page or 1)
    presentation = bool(presentation_mode)

    if trigger == "invoice-filter-outstanding":
        mode = "outstanding"
        page = 1
    elif trigger == "invoice-filter-settled":
        mode = "settled"
        page = 1
    elif trigger == "invoice-filter-all":
        mode = "all"
        page = 1
    elif trigger in {"invoice-search", "auth-user"}:
        page = 1
    elif trigger == "invoice-page-prev":
        page = max(1, page - 1)
    elif trigger == "invoice-page-next":
        page = page + 1
    elif trigger == "invoice-presentation-toggle":
        presentation = not presentation

    return _render_invoice_register(
        user,
        mode=mode,
        search_value=search_value,
        page=page,
        presentation=presentation,
        action_result=None,
    )


@callback(
    Output("invoice-action-result", "children", allow_duplicate=True),
    Output("invoice-filter-mode", "data", allow_duplicate=True),
    Output("invoice-page", "data", allow_duplicate=True),
    Output("invoice-presentation-mode", "data", allow_duplicate=True),
    Output("invoice-filter-all", "className", allow_duplicate=True),
    Output("invoice-filter-outstanding", "className", allow_duplicate=True),
    Output("invoice-filter-settled", "className", allow_duplicate=True),
    Output("invoice-filter-outstanding", "children", allow_duplicate=True),
    Output("invoice-register-summary", "children", allow_duplicate=True),
    Output("invoice-table-wrap", "children", allow_duplicate=True),
    Output("invoice-page-status", "children", allow_duplicate=True),
    Output("invoice-page-prev", "disabled", allow_duplicate=True),
    Output("invoice-page-next", "disabled", allow_duplicate=True),
    Output("invoice-register-card", "className", allow_duplicate=True),
    Input({"type": "settle-invoice", "id": ALL}, "n_clicks"),
    State("invoice-filter-mode", "data"),
    State("invoice-search", "value"),
    State("invoice-page", "data"),
    State("invoice-presentation-mode", "data"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def settle_invoice(_clicks, filter_mode, search_value, page, presentation_mode, user):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict):
        return (no_update,) * 13
    invoice = repository.settle_invoice(trigger["id"])
    notice = html.Div(
        [
            html.Div(f"Invoice {invoice['invoice_number']} marked settled.", className="notice success"),
            dcc.Link("Issue cargo release on Reviewed BL", href="/reviewed-bl#active-reviewed-bls", className="btn-secondary"),
        ],
        className="stack compact",
    )
    mode = filter_mode or "all"
    result = _render_invoice_register(
        user,
        mode=mode,
        search_value=search_value,
        page=page,
        presentation=bool(presentation_mode),
        action_result=notice,
    )
    return (
        result[13],
        result[0],
        result[1],
        result[2],
        result[3],
        result[4],
        result[5],
        result[6],
        result[7],
        result[8],
        result[9],
        result[10],
        result[11],
        result[12],
    )


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
