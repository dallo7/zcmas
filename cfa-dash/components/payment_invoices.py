"""Colored invoice register for the Check-out (payment) module."""

from __future__ import annotations

from dash import html

from components.icons import icon
from components.ui import badge
from services import repository


def _invoice_type_label(invoice_type: str) -> str:
    return (invoice_type or "").replace("_", " ").title()


def _capitalpay_number(invoice: dict) -> str:
    return repository.invoice_capitalpay_number(invoice)


def _pay_url(invoice: dict) -> str | None:
    return repository.invoice_pay_url(invoice)


def payment_invoices_table(invoices: list[dict], *, show_company: bool = False) -> html.Table:
    headers = [
        "Invoice",
        "Settlement",
        "BL",
        "Z-SAD",
        "Amount due",
        "CapitalPay No",
    ]
    if show_company:
        headers.append("Company")
    headers.extend(["Status", "Actions"])

    body_rows = []
    for inv in invoices:
        inv_type = inv.get("invoice_type") or ""
        row_class = (
            "payment-invoice-row payment-invoice-row--full"
            if inv_type == "FULL_SETTLEMENT"
            else "payment-invoice-row payment-invoice-row--service"
        )
        type_class = (
            "payment-type-pill payment-type-pill--full"
            if inv_type == "FULL_SETTLEMENT"
            else "payment-type-pill payment-type-pill--service"
        )
        amount = repository.invoice_gn83_total(inv)
        pay_url = _pay_url(inv)
        pay_control = (
            html.A(
                icon("lucide:credit-card", 15),
                href=pay_url,
                target="_blank",
                className="payment-action-link payment-action-link--pay",
                title="Pay here",
                **{"aria-label": "Pay here"},
            )
            if pay_url
            else html.Span(
                icon("lucide:credit-card", 15),
                className="payment-action-link payment-action-link--disabled",
                title="Pay here",
                **{"aria-label": "Pay here"},
            )
        )
        actions = html.Div(
            [
                html.A(
                    icon("lucide:file-down", 15),
                    href=repository.invoice_download_url(inv["id"]),
                    target="_blank",
                    className="payment-action-link payment-action-link--pdf",
                    title="Download PDF",
                    **{"aria-label": "Download PDF"},
                ),
                pay_control,
                html.A(
                    icon("ic:baseline-whatsapp", 17),
                    href=repository.invoice_whatsapp_link(inv["id"]),
                    target="_blank",
                    className="payment-action-link payment-action-link--share",
                    title="WhatsApp",
                    **{"aria-label": "WhatsApp"},
                ),
            ],
            className="payment-invoice-actions",
        )
        cells = [
            html.Td(
                html.Div(
                    [
                        html.Div(
                            f"ZCAMS {_invoice_type_label(inv_type)} Invoice",
                            className="payment-invoice-kicker",
                        ),
                        html.Div(inv["invoice_number"], className="payment-invoice-number mono"),
                    ],
                    className="payment-invoice-title",
                ),
            ),
            html.Td(html.Span(_invoice_type_label(inv_type), className=type_class)),
            html.Td(inv.get("bl_number") or "-", className="mono"),
            html.Td(inv.get("z_sad_number") or "-", className="mono payment-zsad"),
            html.Td(html.Strong(f"USD {amount:,.2f}", className="payment-amount-due")),
            html.Td(_capitalpay_number(inv), className="mono payment-capitalpay-ref"),
        ]
        if show_company:
            cells.append(html.Td(inv.get("company_name") or "-"))
        cells.extend([html.Td(badge(inv.get("status") or "DRAFT")), html.Td(actions)])
        body_rows.append(html.Tr(cells, className=row_class))

    return html.Table(
        [
            html.Thead(html.Tr([html.Th(h) for h in headers], className="payment-invoices-head")),
            html.Tbody(
                body_rows
                if body_rows
                else [
                    html.Tr(
                        html.Td(
                            "No invoices issued yet. Create an invoice from Reviewed BL.",
                            colSpan=len(headers),
                            className="muted payment-invoices-empty",
                        )
                    )
                ]
            ),
        ],
        className="data-table payment-invoices-table",
    )
