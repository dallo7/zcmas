from dash import Input, Output, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate

from components.icons import icon
from components.layout import header
from components.payment_invoices import payment_invoices_table
from components.workflow import shortcut_chip
from services import repository


register_page(__name__, path="/checkout", name="Check-out")


def layout(**_kwargs):
    return html.Div(
        [
            header(
                "Check-out",
                actions=[
                    dcc.Link([icon("lucide:receipt", 14), "Invoice register"], href="/invoices", className="btn-secondary"),
                ],
                help_text="Review issued invoices, download signed PDFs, and open CapitalPay payment links for your company.",
                pathname="/checkout",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            shortcut_chip("Back to invoices", "/invoices", "lucide:receipt"),
                            shortcut_chip("Request invoice", "/reviewed-bl#active-reviewed-bls", "lucide:file-check-2", "primary"),
                        ],
                        className="shortcut-row",
                    ),
                    html.Div(id="checkout-summary"),
                    html.Div(
                        [
                            html.H2("Payment register"),
                            html.P(
                                "All ZCAMS invoices for your company with BL, Z-SAD, amount due, "
                                "CapitalPay reference, and payment actions.",
                                className="muted",
                            ),
                            html.Div(id="checkout-invoice-table"),
                        ],
                        className="card section-card payment-register-card",
                    ),
                ],
                className="page-content stack",
            ),
        ]
    )


def _checkout_summary(invoices: list[dict]) -> html.Div:
    awaiting = sum(1 for inv in invoices if inv.get("status") == "AWAITING_PAYMENT")
    settled = sum(1 for inv in invoices if inv.get("status") == "SETTLED")
    outstanding_total = sum(
        repository.invoice_gn83_total(inv)
        for inv in invoices
        if inv.get("status") != "SETTLED"
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Span(str(len(invoices)), className="checkout-stat-value"),
                    html.Span("Total invoices", className="checkout-stat-label"),
                ],
                className="checkout-stat checkout-stat--total",
            ),
            html.Div(
                [
                    html.Span(str(awaiting), className="checkout-stat-value"),
                    html.Span("Awaiting payment", className="checkout-stat-label"),
                ],
                className="checkout-stat checkout-stat--awaiting",
            ),
            html.Div(
                [
                    html.Span(str(settled), className="checkout-stat-value"),
                    html.Span("Settled", className="checkout-stat-label"),
                ],
                className="checkout-stat checkout-stat--settled",
            ),
            html.Div(
                [
                    html.Span(f"USD {outstanding_total:,.2f}", className="checkout-stat-value"),
                    html.Span("Outstanding amount", className="checkout-stat-label"),
                ],
                className="checkout-stat checkout-stat--amount",
            ),
        ],
        className="checkout-stats-row",
    )


@callback(
    Output("checkout-summary", "children"),
    Output("checkout-invoice-table", "children"),
    Input("_pages_location", "pathname"),
    Input("auth-user", "data"),
    prevent_initial_call=False,
)
def render_checkout_register(pathname, user):
    if (pathname or "") != "/checkout":
        raise PreventUpdate
    invoices = repository.list_invoices_for_user(user)
    show_company = bool(user and user.get("role") == "SUPER_ADMIN")
    subtitle = (
        "Platform view: all invoices issued across registered CFAs."
        if show_company
        else "Company view: invoices for your CFA only."
    )
    return (
        _checkout_summary(invoices),
        html.Div(
            [
                html.P(subtitle, className="checkout-scope-note"),
                payment_invoices_table(invoices, show_company=show_company),
            ],
        ),
    )
