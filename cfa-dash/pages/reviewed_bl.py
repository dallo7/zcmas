import logging
import traceback
from pathlib import Path

from dash import ALL, Input, Output, State, callback, clientside_callback, ctx, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate

from components.icons import icon
from components.layout import header
from components.ui import badge, status_table
from components.workflow import next_step_banner, shortcut_chip
from services import repository
from services.db import UPLOAD_DIR
from services.gn83 import gn83_quote_for_reviewed


# File-based logger for the invoice request flow so failures are persisted
# even when the host shell swallows stderr (Windows PowerShell wrapper).
_INVOICE_LOG_PATH = Path(UPLOAD_DIR).parent / "invoice_flow.log"
_invoice_logger = logging.getLogger("zcams.invoice_flow")
if not _invoice_logger.handlers:
    _invoice_logger.setLevel(logging.INFO)
    try:
        _INVOICE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _handler = logging.FileHandler(_INVOICE_LOG_PATH, encoding="utf-8")
        _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _invoice_logger.addHandler(_handler)
    except OSError:
        pass


register_page(__name__, path="/reviewed-bl", name="Reviewed BL")


def layout(**_kwargs):
    bls = repository.list_bls()
    reviewed = repository.list_reviewed_bls()
    reviewed_history = repository.list_reviewed_bls(include_cancelled=True)
    return html.Div(
        [
            header(
                "Reviewed BL & Z-SAD",
                actions=[
                    dcc.Link([icon("lucide:file-up", 14), "Upload BL"], href="/bls", className="btn-secondary"),
                    dcc.Link([icon("lucide:receipt", 14), "Invoices"], href="/invoices", className="btn-secondary"),
                ],
                help_text="Review uploaded BLs, manage single-use Z-SAD numbers, replace Z-SADs when corrections are needed, and move records to invoicing.",
                pathname="/reviewed-bl",
            ),
            html.Div(
                [
                    html.Div(id="review-action-result"),
                    # These satisfy BL-page outputs reused by the invoice modal callback.
                    # Without local placeholders, Reviewed BL row clicks fail because
                    # Dash cannot update components that are absent from the active page.
                    html.Div(id="bl-result", style={"display": "none"}),
                    html.Div(id="bl-table", style={"display": "none"}),
                    html.Div(
                        [
                            html.H2("BLs Awaiting Review"),
                            html.Div(id="awaiting-review-table", children=_awaiting_table(bls)),
                        ],
                        className="card section-card",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2("Active Reviewed BLs"),
                                    html.P(
                                        "Each BL keeps one active Z-SAD. Use Replace BL to retire the current number, "
                                        "cancel outstanding invoices, and move the BL out of the active workflow for re-upload.",
                                        className="muted section-lead",
                                    ),
                                ],
                                className="section-heading-block",
                            ),
                            html.Div(id="reviewed-bl-table", children=_reviewed_table(reviewed)),
                        ],
                        id="active-reviewed-bls",
                        className="card section-card",
                    ),
                    html.Div(
                        [
                            html.H2("Z-SAD & Invoice History"),
                            html.P("Superseded Z-SAD numbers and cancelled invoices remain in the audit trail.", className="muted section-lead"),
                            html.Div(id="zsad-history-table", children=_zsad_history_table(reviewed_history)),
                        ],
                        className="card section-card",
                    ),
                    html.Div(
                        [
                            shortcut_chip("Upload another BL", "/bls", "lucide:file-up"),
                            shortcut_chip("Outstanding payments", "/checkout", "lucide:credit-card", "accent"),
                        ],
                        className="shortcut-row",
                    ),
                ],
                className="page-content stack",
            ),
        ]
    )


def _awaiting_table(bls):
    pending = [bl for bl in bls if bl["status"] == "UPLOADED"]
    return status_table(
        ["BL Number", "Route", "Consignee", "Action"],
        [
            [
                bl["bl_number"],
                bl["route_type"],
                bl.get("consignee_name") or "-",
                html.Button("Review & Issue Z-SAD", id={"type": "review-bl", "id": bl["id"]}, className="btn-secondary"),
            ]
            for bl in pending
        ],
    )


def _zsad_active_badge(item: dict) -> html.Span:
    if int(item.get("is_active") or 0) == 1:
        return html.Span("Active", className="badge badge-approved")
    return html.Span("Superseded", className="badge badge-applied")


def _reviewed_table(reviewed):
    def latest_invoice(item: dict) -> dict:
        return repository.row(
            """
            SELECT inv.*, pay.secure_link, pay.capitalpay_ref
            FROM invoices inv
            LEFT JOIN payments pay ON pay.invoice_id = inv.id
            WHERE inv.reviewed_bl_id = ? AND inv.status != 'CANCELLED'
            ORDER BY inv.created_at DESC
            LIMIT 1
            """,
            (item["id"],),
        ) or {}

    return status_table(
        ["BL Number", "Active Z-SAD", "Consignee TIN", "Status", "Actions"],
        [
            [
                item["bl_number"],
                html.Div(
                    [
                        html.Strong(item.get("z_sad_number") or "-"),
                        html.Span("Single-use", className="zsad-tag"),
                    ],
                    className="zsad-cell",
                ),
                item.get("consignee_tin") or "-",
                badge(item["status"]),
                _reviewed_actions(item, latest_invoice(item)),
            ]
            for item in reviewed
        ],
    )


def _reviewed_actions(item: dict, invoice: dict):
    has_active_zsad = bool(item.get("z_sad_number")) and int(item.get("is_active") or 0) == 1
    can_invoice = has_active_zsad and item["status"] not in {"CARGO_RELEASED", "CANCELLED"}
    pay_href = repository.invoice_pay_url(invoice) if invoice else None
    return html.Div(
        [
            html.Button(
                "Service",
                id={"type": "invoice-request", "id": item["id"], "variant": "service"},
                className="btn-primary",
                type="button",
                n_clicks=0,
                disabled=not can_invoice,
                title="Generate GN 83 service-fee invoice",
            ),
            html.Button(
                "Full Settlement",
                id={"type": "invoice-request", "id": item["id"], "variant": "full"},
                className="btn-secondary",
                type="button",
                n_clicks=0,
                disabled=not can_invoice,
                title="Generate GN 83 full-settlement invoice",
            ),
            html.Button(
                "Replace BL",
                id={"type": "detach-open", "id": item["id"]},
                className="btn-secondary",
                type="button",
                n_clicks=0,
                disabled=not has_active_zsad or item["status"] == "CARGO_RELEASED",
                title="Retire active Z-SAD, cancel open invoices, and cancel this BL so it can be uploaded again",
            ),
            html.Button(
                "Issue Release",
                id={"type": "issue-release", "id": item["id"]},
                className="btn-secondary",
                type="button",
                n_clicks=0,
                disabled=item["status"] != "SETTLED_RELEASE_PENDING",
            ),
            html.A(
                "Pay",
                href=pay_href or "/checkout",
                target="_blank" if pay_href else None,
                className="btn-secondary",
                title="Open CapitalPay checkout" if pay_href else "Open Check-out register",
            )
            if item["status"] == "AWAITING_PAYMENT" or pay_href
            else None,
        ],
        className="row-actions wrap",
    )


def _zsad_history_table(reviewed):
    rows_data = []
    for item in reviewed:
        history = repository.list_z_sad_history(item["id"])
        is_replaced_bl = item.get("status") == "CANCELLED"
        if not is_replaced_bl and len(history) <= 1 and not any(h.get("invoice_count") for h in history):
            continue
        for entry in history:
            rows_data.append(
                [
                    repository.display_bl_number(item),
                    entry.get("z_sad_number") or "-",
                    _zsad_active_badge(entry),
                    entry.get("generated_at", "-")[:10] if entry.get("generated_at") else "-",
                    str(entry.get("invoice_count") or 0),
                    str(entry.get("open_invoices") or 0),
                ]
            )
    if not rows_data:
        return html.Div("No Z-SAD replacements recorded yet.", className="muted empty-state")
    return status_table(
        ["BL Number", "Z-SAD Number", "Status", "Issued", "Invoices", "Open"],
        rows_data,
    )


def detach_zsad_modal():
    return html.Div(
        html.Div(
            [
                html.Div(
                    [
                        html.H2("Replace BL"),
                        html.Button("×", id="detach-modal-close", className="modal-close", title="Close"),
                    ],
                    className="modal-header",
                ),
                html.Div(id="detach-modal-body", className="detach-modal-body"),
                html.Div(
                    [
                        dcc.Checklist(
                            id="detach-confirm-check",
                            options=[
                                {
                                    "label": (
                                        "I confirm the active Z-SAD should be retired, listed invoices cancelled, "
                                        "and this BL cancelled so it can be uploaded again."
                                    ),
                                    "value": "CONFIRMED",
                                }
                            ],
                            value=[],
                            className="invoice-confirm-check",
                        ),
                    ],
                    id="detach-confirm-panel",
                    className="invoice-confirm-panel",
                ),
                html.Div(
                    [
                        html.Button("Cancel", id="detach-modal-close-secondary", className="btn-secondary"),
                        html.Button(
                            "Confirm BL cancellation",
                            id="detach-modal-submit",
                            className="btn-primary",
                            title="Retire Z-SAD, cancel BL journey, and allow re-upload",
                        ),
                    ],
                    className="modal-actions",
                ),
            ],
            className="invoice-modal-card detach-modal-card",
        ),
        id="detach-zsad-modal",
        className="modal-backdrop is-hidden",
    )


def _detach_preview_body(preview: dict) -> list:
    if not preview.get("can_detach"):
        return [
            html.Div(
                [
                    icon("lucide:shield-alert", 18),
                    html.Div(
                        [
                            html.Strong("Replacement not available"),
                            html.P(preview.get("block_reason") or "This BL cannot receive a new Z-SAD in its current state."),
                        ],
                    ),
                ],
                className="detach-blocked",
            )
        ]

    open_invoices = preview.get("open_invoices") or []
    history = preview.get("history") or []
    return [
        html.Div(
            [
                html.Div("Bill of Lading", className="invoice-kicker"),
                html.Strong(preview.get("bl_number") or "-"),
            ],
            className="invoice-reference-card",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Span("Current Z-SAD (will be retired)", className="detach-label"),
                        html.Strong(preview.get("current_zsad") or "-", className="detach-old-zsad"),
                    ],
                    className="detach-zsad-row",
                ),
                html.Div(
                    [
                        icon("lucide:arrow-down", 16),
                        html.Span("This BL journey will be cancelled so the BL number can be uploaded again"),
                    ],
                    className="detach-flow-arrow muted",
                ),
            ],
            className="detach-flow-card",
        ),
        html.Div(
            [
                html.H4("What happens next"),
                html.Ul(
                    [
                        html.Li("The current Z-SAD is marked superseded and must not be used for customs filing."),
                        html.Li(
                            f"{len(open_invoices)} open invoice(s) and linked CapitalPay payment(s) will be marked Cancelled."
                            if open_invoices
                            else "No open invoices will be cancelled."
                        ),
                        html.Li("The uploaded BL record is marked Cancelled and detached from the active workflow."),
                        html.Li("Upload the corrected BL again, then issue a fresh Z-SAD from the BL flow."),
                    ],
                    className="detach-checklist",
                ),
            ],
            className="detach-impact-panel",
        ),
        html.Div(
            [
                html.H4("Open invoices to cancel"),
                status_table(
                    ["Invoice", "Type", "Status", "Amount"],
                    [
                        [
                            inv["invoice_number"],
                            inv["invoice_type"].replace("_", " ").title(),
                            badge(inv["status"]),
                            repository.money(inv.get("total")),
                        ]
                        for inv in open_invoices
                    ],
                )
                if open_invoices
                else html.P("No open invoices on this BL.", className="muted"),
            ],
            className="detach-invoices-panel",
        )
        if open_invoices
        else None,
        html.Div(
            [
                html.H4("Z-SAD history for this BL"),
                status_table(
                    ["Z-SAD", "Status", "Issued"],
                    [
                        [
                            entry.get("z_sad_number") or "-",
                            _zsad_active_badge(entry),
                            (entry.get("generated_at") or "-")[:10],
                        ]
                        for entry in history
                    ],
                ),
            ],
            className="detach-history-panel",
        )
        if len(history) > 1
        else None,
    ]


def _detach_success_notice(updated: dict) -> html.Div:
    summary = updated.get("detach_summary") or {}
    cancelled = summary.get("cancelled_invoices") or []
    if not summary.get("new_zsad"):
        display_bl = repository.display_bl_number(updated)
        return html.Div(
            [
                next_step_banner(
                    f"BL {display_bl} cancelled and detached. "
                    f"Retired Z-SAD {summary.get('old_zsad')}.",
                    dcc.Link("Upload corrected BL", href="/bls", className="btn-primary"),
                    dcc.Link("View reviewed BLs", href="/reviewed-bl#active-reviewed-bls", className="btn-secondary"),
                ),
                html.P(
                    f"{summary.get('cancelled_count', 0)} invoice(s) marked Cancelled."
                    + (f" ({', '.join(cancelled)})" if cancelled else ""),
                    className="muted",
                ),
            ],
            className="stack compact",
        )
    return html.Div(
        [
            next_step_banner(
                f"Z-SAD replaced for {updated.get('bl_number')}. "
                f"Retired {summary.get('old_zsad')} → Active {summary.get('new_zsad')}.",
                dcc.Link("Request new invoice", href="/reviewed-bl#active-reviewed-bls", className="btn-primary"),
                dcc.Link("View invoices", href="/invoices", className="btn-secondary"),
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Retired Z-SAD", className="detach-label"),
                            html.Strong(summary.get("old_zsad") or "-"),
                            html.Span("Superseded", className="badge badge-applied"),
                        ],
                        className="detach-summary-card old",
                    ),
                    html.Div(
                        [
                            html.Span("New active Z-SAD", className="detach-label"),
                            html.Strong(summary.get("new_zsad") or "-"),
                            html.Span("Active", className="badge badge-approved"),
                        ],
                        className="detach-summary-card new",
                    ),
                ],
                className="detach-summary-row",
            ),
            html.P(
                f"{summary.get('cancelled_count', 0)} invoice(s) marked Cancelled."
                + (f" ({', '.join(cancelled)})" if cancelled else ""),
                className="muted",
            ),
        ],
        className="stack compact",
    )


_CHOOSE_VISIBLE = {"display": "grid", "gap": "14px"}
_CHOOSE_HIDDEN = {"display": "none"}
_DETAILS_VISIBLE = {"display": "grid", "gap": "14px"}
_DETAILS_HIDDEN = {"display": "none"}
_SUBMIT_HIDDEN = {"display": "none"}
_SUBMIT_VISIBLE = {"display": "inline-flex"}
_MODAL_VISIBLE = {"display": "flex", "position": "fixed", "inset": 0, "zIndex": 1200}
_MODAL_HIDDEN = {"display": "none"}


def _invoice_modal_close_outputs():
    """Return the 20-tuple for outputs #1..#20 (see _invoice_modal_open_outputs)."""
    return (
        None,
        "modal-backdrop is-hidden",
        _MODAL_HIDDEN,
        "choose",
        _CHOOSE_VISIBLE,
        _DETAILS_HIDDEN,
        _SUBMIT_HIDDEN,
        no_update,
        "",
        no_update,
        "",
        "",
        "",
        [],
        "",
        "",
        ["WHATSAPP"],
        None,
        None,
        None,
    )


def _invoice_modal_open_outputs(reviewed_id: str, variant: str = "choose"):
    """Return the 20-tuple that toggle_invoice_modal needs for outputs #1..#20.

    The callback exposes 22 outputs total; callers append the trailing
    ``(bl-table, bl-result)`` pair separately.

    Output order (must mirror the @callback decorator):
        1  invoice-request-reviewed.data
        2  invoice-request-modal.className
        3  invoice-request-modal.style
        4  invoice-modal-step.data
        5  invoice-step-choose.style
        6  invoice-step-details.style
        7  invoice-request-submit.style
        8  invoice-settlement-mode.data
        9  invoice-settlement-label.children
        10 invoice-full-amount.value
        11 invoice-beneficiary-name.value
        12 invoice-beneficiary-bank.value
        13 invoice-beneficiary-account.value
        14 invoice-bank-confirm.value
        15 invoice-contact-phone.value
        16 invoice-contact-email.value
        17 invoice-share-channels.value
        18 invoice-request-result.children
        19 invoice-open-request.data
        20 invoice-settlement-pick.data
    """
    reviewed = repository.get_reviewed_bl(reviewed_id)
    if not reviewed:
        raise PreventUpdate
    minimum = minimum_invoice_amount(reviewed)
    if variant == "service":
        return (
            {"id": reviewed_id, "minimum": minimum},
            "modal-backdrop",
            _MODAL_VISIBLE,
            "details",
            _CHOOSE_HIDDEN,
            _DETAILS_VISIBLE,
            _SUBMIT_VISIBLE,
            "SERVICE_FEE_ONLY",
            "Service Fee Only",
            minimum,
            "",
            "",
            "",
            [],
            "",
            "",
            ["WHATSAPP"],
            None,
            None,
            None,
        )
    if variant == "full":
        return (
            {"id": reviewed_id, "minimum": minimum},
            "modal-backdrop",
            _MODAL_VISIBLE,
            "details",
            _CHOOSE_HIDDEN,
            _DETAILS_VISIBLE,
            _SUBMIT_VISIBLE,
            "FULL_SETTLEMENT",
            "Full Settlement",
            minimum,
            "",
            "",
            "",
            [],
            "",
            "",
            ["WHATSAPP"],
            None,
            None,
            None,
        )
    return (
        {"id": reviewed_id, "minimum": minimum},
        "modal-backdrop",
        _MODAL_VISIBLE,
        "choose",
        _CHOOSE_VISIBLE,
        _DETAILS_HIDDEN,
        _SUBMIT_HIDDEN,
        "SERVICE_FEE_ONLY",
        "",
        minimum,
        "",
        "",
        "",
        [],
        "",
        "",
        ["WHATSAPP"],
        None,
        None,
        None,
    )


def invoice_request_modal():
    return html.Div(
        html.Div(
            [
                html.Div(
                    [
                        html.H2("Request Invoice"),
                        html.Button("x", id="invoice-modal-close", className="modal-close", title="Close"),
                    ],
                    className="modal-header",
                ),
                html.Div(
                    [
                        html.Div("Z-SAD", className="invoice-kicker"),
                        html.Strong(id="invoice-modal-zsad"),
                        html.Span(id="invoice-modal-bl"),
                    ],
                    className="invoice-reference-card",
                ),
                html.Div(
                    [
                        html.H3("Choose settlement type"),
                        html.P(
                            "Select Service Fee Only or Full Settlement. You will complete the invoice details, "
                            "then download and share with the importer.",
                            className="muted section-lead",
                        ),
                        html.Div(
                            [
                                html.Button(
                                    [
                                        html.Strong("Service Fee Only"),
                                        html.Span("GN 83 admin fee (20%) plus VAT on the fee."),
                                    ],
                                    id="invoice-pick-service",
                                    className="settlement-option-card",
                                    type="button",
                                    n_clicks=0,
                                ),
                                html.Button(
                                    [
                                        html.Strong("Full Settlement"),
                                        html.Span("Full GN 83 minimum or higher amount with beneficiary bank details."),
                                    ],
                                    id="invoice-pick-full",
                                    className="settlement-option-card",
                                    type="button",
                                    n_clicks=0,
                                ),
                            ],
                            className="settlement-option-row",
                        ),
                    ],
                    id="invoice-step-choose",
                    className="invoice-step-choose",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Button(
                                    [icon("lucide:arrow-left", 14), "Change settlement type"],
                                    id="invoice-back-to-mode",
                                    className="btn-secondary settlement-back-btn",
                                    n_clicks=0,
                                ),
                                html.Span(id="invoice-settlement-label", className="settlement-mode-pill"),
                            ],
                            className="invoice-step-toolbar",
                        ),
                        html.H3("Invoice details", className="invoice-details-heading"),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Label("Full Settlement Amount"),
                                        dcc.Input(id="invoice-full-amount", type="number", min=0, step=0.01, className="form-control"),
                                        html.Small(id="invoice-amount-hint", className="field-hint"),
                                    ],
                                    className="form-group",
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Label("Beneficiary Full Name"),
                                                dcc.Input(id="invoice-beneficiary-name", className="form-control"),
                                            ],
                                            className="form-group",
                                        ),
                                        html.Div(
                                            [
                                                html.Label("Beneficiary Bank Name"),
                                                dcc.Input(id="invoice-beneficiary-bank", className="form-control"),
                                            ],
                                            className="form-group",
                                        ),
                                    ],
                                    className="form-grid two",
                                ),
                                html.Div(
                                    [
                                        html.Label("Beneficiary Account Number"),
                                        dcc.Input(id="invoice-beneficiary-account", className="form-control"),
                                    ],
                                    className="form-group",
                                ),
                                html.Div(
                                    [
                                        html.H4("Confirm beneficiary bank details"),
                                        html.P(
                                            "Full-settlement invoices will be issued using the beneficiary name, bank name, and account number entered above. Confirm the details carefully before requesting the invoice."
                                        ),
                                        dcc.Checklist(
                                            id="invoice-bank-confirm",
                                            options=[
                                                {
                                                    "label": "I confirm the beneficiary bank details are correct and ready to be used on the invoice.",
                                                    "value": "CONFIRMED",
                                                }
                                            ],
                                            value=[],
                                            className="invoice-confirm-check",
                                        ),
                                    ],
                                    className="invoice-confirm-panel",
                                ),
                            ],
                            id="invoice-full-fields",
                            className="stack compact",
                        ),
                        html.Div(
                            [
                                html.Label("Contact Phone Number"),
                                dcc.Input(id="invoice-contact-phone", placeholder="e.g. 0712345678 or 255712345678", className="form-control"),
                                html.Small("Required for SMS and WhatsApp delivery to the importer.", className="field-hint"),
                            ],
                            className="form-group",
                        ),
                        html.Div(
                            [
                                html.Label("Importer Email (for Mail share)"),
                                dcc.Input(id="invoice-contact-email", type="email", placeholder="importer@example.com", className="form-control"),
                                html.Small("Optional now; required when Mail is selected and SMTP is not configured.", className="field-hint"),
                            ],
                            className="form-group",
                        ),
                        html.Div(
                            [
                                html.Label("Share invoice with importer"),
                                dcc.Checklist(
                                    id="invoice-share-channels",
                                    options=[
                                        {"label": "WhatsApp", "value": "WHATSAPP"},
                                        {"label": "TXT / SMS", "value": "SMS"},
                                        {"label": "Mail", "value": "EMAIL"},
                                    ],
                                    value=["WHATSAPP"],
                                    className="invoice-share-checklist",
                                ),
                            ],
                            className="form-group",
                        ),
                        html.Div(id="invoice-breakdown-preview", className="invoice-breakdown"),
                        html.Div([html.Strong("Total Invoice"), html.Strong(id="invoice-total-preview")], className="invoice-total-row"),
                        dcc.Loading(
                            id="invoice-request-result-loading",
                            type="circle",
                            children=html.Div(id="invoice-request-result"),
                        ),
                        dcc.Download(id="invoice-pdf-download"),
                        dcc.Store(id="invoice-share-whatsapp-url"),
                        dcc.Store(id="invoice-pay-now-checkout-url"),
                    ],
                    className="invoice-settlement-card",
                    id="invoice-step-details",
                    style={"display": "none"},
                ),
                html.Div(
                    [
                        html.Button("Close", id="invoice-modal-close-secondary", className="btn-secondary"),
                        html.Button(
                            "Generate & share invoice",
                            id="invoice-request-submit",
                            className="btn-primary",
                            type="button",
                            style={"display": "none"},
                        ),
                        html.Button(
                            "Pay Now",
                            id="invoice-pay-now-submit",
                            className="btn-secondary",
                            type="button",
                            style={"display": "none"},
                        ),
                    ],
                    className="modal-actions",
                ),
            ],
            className="invoice-modal-card",
        ),
        id="invoice-request-modal",
        className="modal-backdrop is-hidden",
        style=_MODAL_HIDDEN,
    )


def _refresh_reviewed_views():
    bls = repository.list_bls()
    reviewed = repository.list_reviewed_bls()
    reviewed_history = repository.list_reviewed_bls(include_cancelled=True)
    return _awaiting_table(bls), _reviewed_table(reviewed), _zsad_history_table(reviewed_history)


@callback(
    Output("review-action-result", "children"),
    Output("awaiting-review-table", "children"),
    Output("reviewed-bl-table", "children"),
    Output("zsad-history-table", "children"),
    Input({"type": "review-bl", "id": ALL}, "n_clicks"),
    Input({"type": "issue-release", "id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def reviewed_row_actions(*_clicks):
    from dash import ctx

    trigger = ctx.triggered_id
    if not isinstance(trigger, dict):
        return no_update, no_update, no_update, no_update
    action = trigger["type"]
    target = trigger["id"]
    if action == "review-bl":
        reviewed = repository.review_bl(target)
        notice = html.Div(f"Z-SAD issued: {reviewed['z_sad_number']}", className="notice success")
    elif action == "issue-release":
        repository.issue_cargo_release(target)
        notice = html.Div("Cargo release issued.", className="notice success")
    else:
        return no_update, no_update, no_update, no_update
    awaiting, table, history = _refresh_reviewed_views()
    return notice, awaiting, table, history


@callback(
    Output("detach-reviewed-id", "data"),
    Output("detach-zsad-modal", "className"),
    Output("detach-modal-body", "children"),
    Output("detach-confirm-check", "value"),
    Output("detach-modal-submit", "disabled"),
    Output("detach-confirm-panel", "style"),
    Output("detach-modal-submit", "style"),
    Input({"type": "detach-open", "id": ALL}, "n_clicks"),
    Input("detach-modal-close", "n_clicks"),
    Input("detach-modal-close-secondary", "n_clicks"),
    State({"type": "detach-open", "id": ALL}, "id"),
    prevent_initial_call=True,
)
def toggle_detach_modal(detach_clicks, _close, _close_secondary, detach_ids):
    from dash import ctx

    trigger = ctx.triggered_id
    if isinstance(trigger, str) and trigger in {"detach-modal-close", "detach-modal-close-secondary"}:
        return None, "modal-backdrop is-hidden", None, [], True, {}, {}
    if not isinstance(trigger, dict):
        return (no_update,) * 7
    clicked_id = trigger.get("id")
    clicked_count = 0
    for button_id, clicks in zip(detach_ids or [], detach_clicks or []):
        if clicks and button_id.get("id") == clicked_id:
            clicked_id = button_id["id"]
            clicked_count = clicks
            break
    if not clicked_id or not clicked_count:
        raise PreventUpdate
    preview = repository.get_zsad_detach_preview(clicked_id)
    body = _detach_preview_body(preview)
    can_detach = bool(preview.get("can_detach"))
    confirm_style = {} if can_detach else {"display": "none"}
    submit_style = {} if can_detach else {"display": "none"}
    return clicked_id, "modal-backdrop", body, [], True, confirm_style, submit_style


@callback(
    Output("detach-reviewed-id", "data", allow_duplicate=True),
    Output("detach-zsad-modal", "className", allow_duplicate=True),
    Output("detach-modal-body", "children", allow_duplicate=True),
    Output("detach-confirm-check", "value", allow_duplicate=True),
    Output("detach-modal-submit", "disabled", allow_duplicate=True),
    Output("detach-confirm-panel", "style", allow_duplicate=True),
    Output("detach-modal-submit", "style", allow_duplicate=True),
    Input("_pages_location", "pathname"),
    prevent_initial_call=True,
)
def close_detach_modal_on_navigation(_pathname):
    return None, "modal-backdrop is-hidden", None, [], True, {}, {}


@callback(
    Output("detach-modal-submit", "disabled", allow_duplicate=True),
    Input("detach-confirm-check", "value"),
    State("detach-reviewed-id", "data"),
    prevent_initial_call=True,
)
def enable_detach_submit(confirmed, reviewed_id):
    if not reviewed_id or "CONFIRMED" not in (confirmed or []):
        return True
    preview = repository.get_zsad_detach_preview(reviewed_id)
    return not bool(preview.get("can_detach"))


@callback(
    Output("review-action-result", "children", allow_duplicate=True),
    Output("awaiting-review-table", "children", allow_duplicate=True),
    Output("reviewed-bl-table", "children", allow_duplicate=True),
    Output("zsad-history-table", "children", allow_duplicate=True),
    Output("detach-zsad-modal", "className", allow_duplicate=True),
    Output("detach-reviewed-id", "data", allow_duplicate=True),
    Output("detach-modal-body", "children", allow_duplicate=True),
    Input("detach-modal-submit", "n_clicks"),
    State("detach-reviewed-id", "data"),
    State("detach-confirm-check", "value"),
    prevent_initial_call=True,
)
def submit_detach_zsad(_clicks, reviewed_id, confirmed):
    if not reviewed_id:
        return (no_update,) * 7
    if "CONFIRMED" not in (confirmed or []):
        preview = repository.get_zsad_detach_preview(reviewed_id)
        return (
            html.Div("Confirm BL replacement before continuing.", className="notice error"),
            no_update,
            no_update,
            no_update,
            "modal-backdrop",
            reviewed_id,
            _detach_preview_body(preview),
        )
    try:
        updated = repository.detach_zsad_for_reupload(reviewed_id)
    except ValueError as exc:
        preview = repository.get_zsad_detach_preview(reviewed_id)
        return (
            html.Div(str(exc), className="notice error"),
            no_update,
            no_update,
            no_update,
            "modal-backdrop",
            reviewed_id,
            _detach_preview_body(preview),
        )
    awaiting, table, history = _refresh_reviewed_views()
    return (
        _detach_success_notice(updated),
        awaiting,
        table,
        history,
        "modal-backdrop is-hidden",
        None,
        None,
    )


def _resolve_invoice_reviewed(data, bl_id=None):
    """Resolve reviewed BL context for modal preview and submit."""
    if data and data.get("id"):
        reviewed = repository.get_reviewed_bl(data["id"])
        if reviewed:
            return data, reviewed
    if bl_id:
        row = repository.row("SELECT id FROM reviewed_bls WHERE bl_id = ?", (bl_id,))
        if row:
            reviewed = repository.get_reviewed_bl(row["id"])
            if reviewed:
                minimum = minimum_invoice_amount(reviewed)
                return {"id": reviewed["id"], "minimum": minimum}, reviewed
    return None, None


@callback(
    Output("invoice-request-reviewed", "data"),
    Output("invoice-request-modal", "className"),
    Output("invoice-request-modal", "style"),
    Output("invoice-modal-step", "data"),
    Output("invoice-step-choose", "style"),
    Output("invoice-step-details", "style"),
    Output("invoice-request-submit", "style"),
    Output("invoice-settlement-mode", "data"),
    Output("invoice-settlement-label", "children"),
    Output("invoice-full-amount", "value"),
    Output("invoice-beneficiary-name", "value"),
    Output("invoice-beneficiary-bank", "value"),
    Output("invoice-beneficiary-account", "value"),
    Output("invoice-bank-confirm", "value"),
    Output("invoice-contact-phone", "value"),
    Output("invoice-contact-email", "value"),
    Output("invoice-share-channels", "value"),
    Output("invoice-request-result", "children"),
    Output("invoice-open-request", "data", allow_duplicate=True),
    Output("invoice-settlement-pick", "data", allow_duplicate=True),
    Output("bl-table", "children", allow_duplicate=True),
    Output("bl-result", "children", allow_duplicate=True),
    Input("bl-request-invoice", "n_clicks"),
    State("bl-last-bl-id", "data"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def toggle_invoice_modal(_bl_request_clicks, bl_id, user, *_legacy_args):
    trigger = ctx.triggered_id
    if trigger is None:
        raise PreventUpdate
    if isinstance(trigger, dict) and trigger.get("type") == "invoice-request":
        return _invoice_modal_open_outputs(trigger["id"], trigger.get("variant", "choose")) + (no_update, no_update)
    if trigger == "bl-request-invoice":
        if not bl_id:
            return (no_update,) * 20 + (
                no_update,
                html.Div("Save a BL first, then request an invoice.", className="notice error"),
            )
        try:
            reviewed = repository.review_bl(bl_id)
        except ValueError as exc:
            return (no_update,) * 20 + (no_update, html.Div(str(exc), className="notice error"))

        # Rebuild the BL table only if pages.bls is already loaded in
        # sys.modules. We must NOT trigger a fresh import here — that would
        # re-run dash.register_page() inside a callback, which Dash forbids.
        import sys
        table = no_update
        bls_module = sys.modules.get("pages.bls")
        if bls_module is not None and hasattr(bls_module, "_bl_table"):
            try:
                company_id = (user or {}).get("company_id") or repository.DEMO_COMPANY_ID
                table = bls_module._bl_table(repository.list_bls(company_id))
            except Exception:
                table = no_update

        zsad = reviewed.get("z_sad_number") or "issued"
        notice = html.Div(
            f"Z-SAD {zsad} issued. Choose Service Fee Only or Full Settlement.",
            className="notice success",
        )
        return _invoice_modal_open_outputs(reviewed["id"], "choose") + (table, notice)
    raise PreventUpdate


@callback(
    Output("invoice-request-reviewed", "data", allow_duplicate=True),
    Output("invoice-request-modal", "className", allow_duplicate=True),
    Output("invoice-request-modal", "style", allow_duplicate=True),
    Output("invoice-modal-step", "data", allow_duplicate=True),
    Output("invoice-step-choose", "style", allow_duplicate=True),
    Output("invoice-step-details", "style", allow_duplicate=True),
    Output("invoice-request-submit", "style", allow_duplicate=True),
    Output("invoice-settlement-mode", "data", allow_duplicate=True),
    Output("invoice-settlement-label", "children", allow_duplicate=True),
    Output("invoice-full-amount", "value", allow_duplicate=True),
    Output("invoice-beneficiary-name", "value", allow_duplicate=True),
    Output("invoice-beneficiary-bank", "value", allow_duplicate=True),
    Output("invoice-beneficiary-account", "value", allow_duplicate=True),
    Output("invoice-bank-confirm", "value", allow_duplicate=True),
    Output("invoice-contact-phone", "value", allow_duplicate=True),
    Output("invoice-contact-email", "value", allow_duplicate=True),
    Output("invoice-share-channels", "value", allow_duplicate=True),
    Output("invoice-request-result", "children", allow_duplicate=True),
    Output("invoice-open-request", "data", allow_duplicate=True),
    Output("invoice-settlement-pick", "data", allow_duplicate=True),
    Input("invoice-modal-close", "n_clicks"),
    Input("invoice-modal-close-secondary", "n_clicks"),
    prevent_initial_call=True,
)
def close_invoice_modal(_close, _close_secondary):
    if ctx.triggered_id not in {"invoice-modal-close", "invoice-modal-close-secondary"}:
        raise PreventUpdate
    if not ctx.triggered or not ctx.triggered[0].get("value"):
        raise PreventUpdate
    return _invoice_modal_close_outputs()


@callback(
    Output("invoice-request-reviewed", "data", allow_duplicate=True),
    Output("invoice-request-modal", "className", allow_duplicate=True),
    Output("invoice-request-modal", "style", allow_duplicate=True),
    Output("invoice-modal-step", "data", allow_duplicate=True),
    Output("invoice-step-choose", "style", allow_duplicate=True),
    Output("invoice-step-details", "style", allow_duplicate=True),
    Output("invoice-request-submit", "style", allow_duplicate=True),
    Output("invoice-settlement-mode", "data", allow_duplicate=True),
    Output("invoice-settlement-label", "children", allow_duplicate=True),
    Output("invoice-full-amount", "value", allow_duplicate=True),
    Output("invoice-beneficiary-name", "value", allow_duplicate=True),
    Output("invoice-beneficiary-bank", "value", allow_duplicate=True),
    Output("invoice-beneficiary-account", "value", allow_duplicate=True),
    Output("invoice-bank-confirm", "value", allow_duplicate=True),
    Output("invoice-contact-phone", "value", allow_duplicate=True),
    Output("invoice-contact-email", "value", allow_duplicate=True),
    Output("invoice-share-channels", "value", allow_duplicate=True),
    Output("invoice-request-result", "children", allow_duplicate=True),
    Output("invoice-open-request", "data", allow_duplicate=True),
    Output("invoice-settlement-pick", "data", allow_duplicate=True),
    Input({"type": "invoice-request", "id": ALL, "variant": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_reviewed_invoice_modal(_invoice_clicks):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or trigger.get("type") != "invoice-request":
        raise PreventUpdate
    triggered_value = (ctx.triggered or [{}])[0].get("value")
    if not triggered_value:
        raise PreventUpdate
    return _invoice_modal_open_outputs(trigger["id"], trigger.get("variant", "choose"))


@callback(
    Output("invoice-modal-step", "data", allow_duplicate=True),
    Output("invoice-step-choose", "style", allow_duplicate=True),
    Output("invoice-step-details", "style", allow_duplicate=True),
    Output("invoice-request-submit", "style", allow_duplicate=True),
    Output("invoice-settlement-mode", "data", allow_duplicate=True),
    Output("invoice-settlement-label", "children", allow_duplicate=True),
    Input("invoice-pick-service", "n_clicks"),
    Input("invoice-pick-full", "n_clicks"),
    Input("invoice-back-to-mode", "n_clicks"),
    State("invoice-request-reviewed", "data"),
    prevent_initial_call=True,
)
def invoice_choose_settlement(_service_clicks, _full_clicks, _back_clicks, reviewed_data):
    if not reviewed_data or not reviewed_data.get("id"):
        raise PreventUpdate
    trigger = ctx.triggered_id
    if not ctx.triggered or not ctx.triggered[0].get("value"):
        raise PreventUpdate
    if trigger == "invoice-back-to-mode":
        return "choose", _CHOOSE_VISIBLE, _DETAILS_HIDDEN, _SUBMIT_HIDDEN, no_update, ""
    if trigger == "invoice-pick-service":
        return "details", _CHOOSE_HIDDEN, _DETAILS_VISIBLE, _SUBMIT_VISIBLE, "SERVICE_FEE_ONLY", "Service Fee Only"
    if trigger == "invoice-pick-full":
        return "details", _CHOOSE_HIDDEN, _DETAILS_VISIBLE, _SUBMIT_VISIBLE, "FULL_SETTLEMENT", "Full Settlement"
    raise PreventUpdate


@callback(
    Output("invoice-pay-now-submit", "style"),
    Input("invoice-modal-step", "data"),
    Input("invoice-request-submit", "style"),
)
def toggle_pay_now_button(step, submit_style):
    if step == "details" and submit_style != _SUBMIT_HIDDEN:
        return _SUBMIT_VISIBLE
    return _SUBMIT_HIDDEN


@callback(
    Output("invoice-modal-zsad", "children"),
    Output("invoice-modal-bl", "children"),
    Output("invoice-full-fields", "style"),
    Output("invoice-amount-hint", "children"),
    Output("invoice-total-preview", "children"),
    Output("invoice-breakdown-preview", "children"),
    Input("invoice-request-reviewed", "data"),
    Input("invoice-settlement-mode", "data"),
    Input("invoice-full-amount", "value"),
    Input("invoice-modal-step", "data"),
    State("bl-last-bl-id", "data"),
)
def update_invoice_modal(data, mode, amount, step, bl_id):
    data, reviewed = _resolve_invoice_reviewed(data, bl_id)
    if not reviewed:
        return "-", "", {"display": "none"}, "", "USD 0.00", None
    if step != "details":
        return (
            reviewed.get("z_sad_number") or "-",
            f"BL {reviewed.get('bl_number') or '-'}",
            {"display": "none"},
            "",
            "USD 0.00",
            None,
        )
    minimum = float((data or {}).get("minimum") or minimum_invoice_amount(reviewed))
    std_amount = max(float(amount or minimum), minimum)
    invoice_type = mode or "SERVICE_FEE_ONLY"
    std_for_calc = std_amount if invoice_type == "FULL_SETTLEMENT" else minimum
    calc = repository.calculate_invoice(std_for_calc, invoice_type)
    full_style = {"display": "grid", "gap": "14px"} if invoice_type == "FULL_SETTLEMENT" else {"display": "none"}
    quote = gn83_quote_for_reviewed(reviewed)
    unit_hint = ""
    if quote.get("per_container") and quote.get("units", 1) > 1:
        unit_hint = (
            f" GN 83 applies USD {quote['unit_rate']:,.2f} × {int(quote['units'])} containers "
            f"({quote['category_label']})."
        )
    hint = (
        f"Minimum allowed is USD {minimum:,.2f}.{unit_hint} "
        "You may enter a higher amount for Full Settlement if required."
    )
    breakdown = invoice_breakdown(calc, invoice_type, reviewed)
    return (
        reviewed.get("z_sad_number") or "-",
        f"BL {reviewed.get('bl_number') or '-'}",
        full_style,
        hint,
        f"USD {calc['total']:,.2f}",
        breakdown,
    )


@callback(
    Output("invoice-request-result", "children", allow_duplicate=True),
    Output("invoice-share-whatsapp-url", "data", allow_duplicate=True),
    Input("invoice-request-submit", "n_clicks"),
    State("invoice-request-reviewed", "data"),
    State("invoice-settlement-mode", "data"),
    State("invoice-full-amount", "value"),
    State("invoice-beneficiary-name", "value"),
    State("invoice-beneficiary-bank", "value"),
    State("invoice-beneficiary-account", "value"),
    State("invoice-bank-confirm", "value"),
    State("invoice-contact-phone", "value"),
    State("invoice-contact-email", "value"),
    State("invoice-share-channels", "value"),
    State("bl-last-bl-id", "data"),
    prevent_initial_call=True,
)
def submit_invoice_request(
    _clicks,
    data,
    mode,
    amount,
    beneficiary_name,
    bank_name,
    account_number,
    confirmed,
    phone,
    email,
    share_channels,
    bl_id,
):
    _invoice_logger.info(
        "submit_invoice_request fired: clicks=%s data=%s mode=%s bl_id=%s channels=%s phone=%s email=%s",
        _clicks, data, mode, bl_id, share_channels, phone, email,
    )
    if not _clicks:
        raise PreventUpdate

    data, reviewed = _resolve_invoice_reviewed(data, bl_id)
    if not reviewed:
        _invoice_logger.warning("submit_invoice_request: no reviewed BL resolved")
        return (
            html.Div(
                "Select a reviewed BL before requesting an invoice.",
                className="notice error",
            ),
            no_update,
        )
    reviewed_id = reviewed["id"]
    channels = share_channels or ["WHATSAPP"]
    if {"SMS", "WHATSAPP"} & set(channels) and not str(phone or "").strip():
        return (
            html.Div(
                "Enter a contact phone number for WhatsApp or TXT sharing.",
                className="notice error",
            ),
            no_update,
        )
    if "EMAIL" in channels and not str(email or "").strip():
        return (
            html.Div(
                "Enter the importer email when Mail sharing is selected.",
                className="notice error",
            ),
            no_update,
        )

    invoice_type = mode or "SERVICE_FEE_ONLY"
    std_override = None
    if invoice_type == "FULL_SETTLEMENT":
        required_fields = [beneficiary_name, bank_name, account_number]
        if any(not str(value or "").strip() for value in required_fields):
            return (
                html.Div(
                    "Enter all beneficiary bank details for Full Settlement.",
                    className="notice error",
                ),
                no_update,
            )
        if "CONFIRMED" not in (confirmed or []):
            return (
                html.Div(
                    "Confirm the beneficiary bank details before requesting the invoice.",
                    className="notice error",
                ),
                no_update,
            )
        std_override = float(amount or 0)

    try:
        _invoice_logger.info(
            "Generating invoice for reviewed_id=%s type=%s override=%s",
            reviewed_id, invoice_type, std_override,
        )
        invoice = repository.generate_invoice(
            reviewed_id,
            invoice_type,
            std_min_fee_override=std_override,
            contact_phone=str(phone).strip(),
            contact_email=str(email or "").strip() or None,
            beneficiary_name=str(beneficiary_name or "").strip() or None,
            beneficiary_bank_name=str(bank_name or "").strip() or None,
            beneficiary_account_number=str(account_number or "").strip() or None,
        )
        _invoice_logger.info(
            "Invoice generated: id=%s number=%s urn=%s",
            invoice.get("id"), invoice.get("invoice_number"), invoice.get("capitalpay_urn"),
        )
        share_results = repository.share_invoice_with_importer(
            invoice["id"],
            channels=channels,
            contact_email=str(email or "").strip() or None,
        )
        _invoice_logger.info("Share results: %s", share_results)
    except ValueError as exc:
        _invoice_logger.warning("Invoice generation rejected: %s", exc)
        return html.Div(str(exc), className="notice error"), no_update
    except Exception as exc:  # noqa: BLE001 - surface unexpected failures to the user
        _invoice_logger.exception("Invoice generation failed unexpectedly")
        tb_text = traceback.format_exc(limit=4)
        return (
            html.Div(
                [
                    html.Div(
                        f"Invoice generation failed: {exc.__class__.__name__}: {exc}",
                        className="notice error",
                    ),
                    html.Details(
                        [
                            html.Summary("Technical details"),
                            html.Pre(tb_text, style={"whiteSpace": "pre-wrap", "fontSize": "11px"}),
                        ],
                        open=False,
                    ),
                ]
            ),
            no_update,
        )

    capitalpay_no = invoice.get("capitalpay_urn") or "-"
    invoice_label = invoice["invoice_type"].replace("_", " ").title()
    message = (
        f"{invoice_label} invoice {invoice['invoice_number']} generated for "
        f"{repository.money(invoice['total'])}. CapitalPay ref {capitalpay_no}."
    )
    pdf_url = repository.invoice_download_url(invoice["id"])
    calc = {
        "std_min_fee": float(invoice.get("std_min_fee") or 0),
        "admin_fee": float(invoice.get("admin_fee") or 0),
        "vat": float(invoice.get("vat") or 0),
        "total": float(invoice.get("total") or 0),
    }
    reviewed_row = reviewed
    result = html.Div(
        [
            html.Div(message, className="notice success"),
            html.Div(
                [
                    html.H4("Invoice summary", className="invoice-details-heading"),
                    invoice_breakdown(calc, invoice["invoice_type"], reviewed_row),
                    html.Div(
                        [html.Strong("Total charged"), html.Strong(repository.money(invoice["total"]))],
                        className="invoice-total-row",
                    ),
                ],
                className="invoice-settlement-card",
            ),
            html.A(
                [icon("lucide:download", 14), "Download signed invoice PDF"],
                href=pdf_url,
                target="_blank",
                className="btn-primary",
                id={"type": "invoice-download-link", "id": invoice["id"]},
            ),
            html.Button(
                [icon("lucide:download", 14), "Save PDF to device"],
                id={"type": "invoice-download-btn", "id": invoice["id"]},
                className="btn-secondary",
                type="button",
            ),
            html.P("Share with the importer:", className="field-hint"),
            invoice_share_actions(invoice["id"], share_results),
        ],
        className="stack compact",
    )
    whatsapp_url = (share_results.get("whatsapp") or {}).get("url") if "WHATSAPP" in {c.upper() for c in channels} else None
    return result, whatsapp_url


@callback(
    Output("invoice-request-result", "children", allow_duplicate=True),
    Output("invoice-pay-now-checkout-url", "data", allow_duplicate=True),
    Input("invoice-pay-now-submit", "n_clicks"),
    State("invoice-request-reviewed", "data"),
    State("invoice-settlement-mode", "data"),
    State("invoice-full-amount", "value"),
    State("invoice-beneficiary-name", "value"),
    State("invoice-beneficiary-bank", "value"),
    State("invoice-beneficiary-account", "value"),
    State("invoice-bank-confirm", "value"),
    State("invoice-contact-phone", "value"),
    State("invoice-contact-email", "value"),
    State("bl-last-bl-id", "data"),
    prevent_initial_call=True,
)
def submit_invoice_pay_now(
    _clicks,
    data,
    mode,
    amount,
    beneficiary_name,
    bank_name,
    account_number,
    confirmed,
    phone,
    email,
    bl_id,
):
    if not _clicks:
        raise PreventUpdate
    data, reviewed = _resolve_invoice_reviewed(data, bl_id)
    if not reviewed:
        return html.Div("Select a reviewed BL before paying.", className="notice error"), no_update
    if not str(phone or "").strip():
        return html.Div("Enter a contact phone number before opening checkout.", className="notice error"), no_update

    invoice_type = mode or "SERVICE_FEE_ONLY"
    std_override = None
    if invoice_type == "FULL_SETTLEMENT":
        if any(not str(value or "").strip() for value in [beneficiary_name, bank_name, account_number]):
            return html.Div("Enter all beneficiary bank details for Full Settlement.", className="notice error"), no_update
        if "CONFIRMED" not in (confirmed or []):
            return html.Div("Confirm the beneficiary bank details before paying.", className="notice error"), no_update
        std_override = float(amount or 0)

    try:
        invoice = repository.generate_invoice(
            reviewed["id"],
            invoice_type,
            std_min_fee_override=std_override,
            contact_phone=str(phone).strip(),
            contact_email=str(email or "").strip() or None,
            beneficiary_name=str(beneficiary_name or "").strip() or None,
            beneficiary_bank_name=str(bank_name or "").strip() or None,
            beneficiary_account_number=str(account_number or "").strip() or None,
        )
    except ValueError as exc:
        return html.Div(str(exc), className="notice error"), no_update
    except Exception as exc:  # noqa: BLE001
        _invoice_logger.exception("Pay Now invoice generation failed")
        return html.Div(f"Pay Now failed: {exc.__class__.__name__}: {exc}", className="notice error"), no_update

    checkout_url = repository.invoice_pay_url(invoice)
    result = html.Div(
        [
            html.Div(
                f"Invoice {invoice['invoice_number']} is ready for in-system payment. Open CapitalPay checkout to choose a bank/payment option.",
                className="notice success",
            ),
            html.A(
                [icon("lucide:external-link", 14), "Open CapitalPay Checkout"],
                href=checkout_url or "/checkout",
                target="_blank",
                rel="noopener noreferrer",
                className="btn-primary",
            ),
            html.P(
                f"CapitalPay ref: {invoice.get('capitalpay_urn') or '-'} | Amount: {repository.money(invoice.get('payable_amount') or invoice.get('total') or 0)}",
                className="field-hint",
            ),
        ],
        className="stack compact",
    )
    return result, checkout_url


# Auto-open the WhatsApp share link in a new tab when an invoice is generated
# with the WHATSAPP channel selected. Runs in the same user-gesture context as
# the submit click, so the browser popup blocker permits it. After opening we
# return '' to clear the store and prevent re-opening on subsequent renders.
clientside_callback(
    """
    function(url) {
        if (!url) { return window.dash_clientside.no_update; }
        try { window.open(url, '_blank', 'noopener'); } catch (e) {}
        return '';
    }
    """,
    Output("invoice-share-whatsapp-url", "data", allow_duplicate=True),
    Input("invoice-share-whatsapp-url", "data"),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(url) {
        if (!url) { return window.dash_clientside.no_update; }
        try { window.open(url, '_blank', 'noopener'); } catch (e) {}
        return '';
    }
    """,
    Output("invoice-pay-now-checkout-url", "data", allow_duplicate=True),
    Input("invoice-pay-now-checkout-url", "data"),
    prevent_initial_call=True,
)


def invoice_breakdown(calc: dict, invoice_type: str, reviewed: dict | None = None) -> html.Div:
    rows_list: list[tuple[str, float, bool]] = []
    if invoice_type == "SERVICE_FEE_ONLY":
        quote = gn83_quote_for_reviewed(reviewed) if reviewed else {}
        basis = quote.get("std_min_fee") or calc["std_min_fee"]
        if quote.get("per_container") and quote.get("units", 1) > 1:
            rows_list.append(
                (
                    f"GN 83 basis ({int(quote['units'])} × USD {quote['unit_rate']:,.2f})",
                    basis,
                    True,
                )
            )
        else:
            rows_list.append(("GN 83 basis (reference)", basis, True))
        rows_list.append(("Admin fee (20%)", calc["admin_fee"], False))
        if calc.get("vat", 0) > 0:
            rows_list.append(("VAT (16%)", calc["vat"], False))
    else:
        if reviewed:
            quote = gn83_quote_for_reviewed(reviewed)
            if quote.get("per_container") and quote.get("units", 1) > 1:
                rows_list.append(
                    (
                        f"GN 83 rate ({int(quote['units'])} × USD {quote['unit_rate']:,.2f})",
                        calc["std_min_fee"],
                        False,
                    )
                )
            else:
                rows_list.append(("GN 83 standard minimum", calc["std_min_fee"], False))
        else:
            rows_list.append(("GN 83 standard minimum", calc["std_min_fee"], False))
        rows_list.append(("Admin fee (20%)", calc["admin_fee"], False))
        if calc.get("vat", 0) > 0:
            rows_list.append(("VAT (16%)", calc["vat"], False))
    return html.Div(
        [
            html.Div(
                [
                    html.Span(label, className="muted" if reference else None),
                    html.Strong(f"USD {value:,.2f}"),
                ],
                className="invoice-breakdown-row",
            )
            for label, value, reference in rows_list
        ],
        className="invoice-breakdown",
    )


def invoice_share_actions(invoice_id: str, share_results: dict) -> html.Div:
    buttons = []
    whatsapp = share_results.get("whatsapp", {})
    if whatsapp.get("url"):
        buttons.append(html.A("Open WhatsApp", href=whatsapp["url"], target="_blank", className="btn-primary"))
    sms = share_results.get("sms", {})
    if sms.get("url"):
        buttons.append(html.A("Open TXT / SMS", href=sms["url"], target="_blank", className="btn-secondary"))
    email = share_results.get("email", {})
    if email.get("sent"):
        buttons.append(html.Span("Email sent", className="badge badge-approved"))
    elif email.get("url"):
        buttons.append(html.A("Open Mail", href=email["url"], target="_blank", className="btn-secondary"))
    elif email.get("reason"):
        buttons.append(html.Span(email["reason"], className="muted"))
    if not buttons:
        return html.Div("No share channel selected.", className="muted")
    return html.Div(buttons, className="invoice-share-actions")


def minimum_invoice_amount(reviewed: dict | None) -> float:
    if not reviewed:
        return 0.0
    return float(gn83_quote_for_reviewed(reviewed)["std_min_fee"])


@callback(
    Output("invoice-pdf-download", "data"),
    Input({"type": "invoice-download-btn", "id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def trigger_invoice_pdf_download(_clicks):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or trigger.get("type") != "invoice-download-btn":
        raise PreventUpdate
    if not ctx.triggered or not ctx.triggered[0].get("value"):
        raise PreventUpdate
    invoice_id = trigger["id"]
    invoice = repository.get_invoice(invoice_id)
    if not invoice:
        raise PreventUpdate
    path = repository.ensure_invoice_pdf(invoice_id)
    filename = f"ZCAMS-Invoice-{invoice.get('invoice_number', invoice_id)}.pdf"
    return dcc.send_file(str(path), filename=filename)
