from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate

from components.layout import header, section_label
from components.icons import icon
from components.ui import badge, detail_item, status_table
from services import repository


register_page(__name__, path="/contracts", name="Contracts")


def _field(label: str, component):
    return html.Label([html.Span(label), component], className="form-field")


def layout(**_kwargs):
    return html.Div(
        [
            header(
                "Contracts",
                help_text="Create importer contracts, issue OTP-secured signing links, and preserve signed hash fingerprints.",
                pathname="/contracts",
            ),
            dcc.Store(id="contracts-refresh-token", data=0),
            dcc.Store(id="latest-contract-id"),
            dcc.Store(id="contracts-page", data=1),
            html.Div(
                [
                    html.Div(id="contract-result"),
                    html.Div(id="contract-send-result"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.P("1-step contract form", className="eyebrow"),
                                            html.H2("Create Contract"),
                                            html.P(
                                                "Capture client identity, shipment details, services, fees, and terms in one step.",
                                                className="muted",
                                            ),
                                        ]
                                    ),
                                ],
                                className="section-heading-row",
                            ),
                            section_label(
                                "Client Info",
                                "Identifies the importer or client who will receive and sign the contract.",
                                "lucide:user-round",
                            ),
                            html.Div(
                                [
                                    _field(
                                        "Importer Name",
                                        dcc.Input(id="contract_importer", placeholder="Importer name", className="form-control"),
                                    ),
                                    _field(
                                        "Importer WhatsApp",
                                        dcc.Input(id="contract_phone", placeholder="Importer WhatsApp", className="form-control"),
                                    ),
                                    _field(
                                        "Importer Email",
                                        dcc.Input(id="contract_email", placeholder="Importer email", className="form-control"),
                                    ),
                                ],
                                className="form-grid",
                            ),
                            section_label(
                                "Shipment Details",
                                "Links the contract to the shipment route, BL reference, cargo, origin, and destination.",
                                "lucide:ship",
                            ),
                            html.Div(
                                [
                                    _field(
                                        "Shipment Route",
                                        dcc.Input(
                                            id="contract_shipment_route",
                                            placeholder="Mombasa -> Nairobi -> Kampala",
                                            className="form-control",
                                        ),
                                    ),
                                    _field(
                                        "BL Reference",
                                        dcc.Input(
                                            id="contract_bl_reference",
                                            placeholder="BL-2024-KE-00472",
                                            className="form-control",
                                        ),
                                    ),
                                    _field(
                                        "Cargo",
                                        dcc.Input(
                                            id="contract_cargo",
                                            placeholder="Electronics & Consumer Goods (500 cartons, 12,500 kg)",
                                            className="form-control",
                                        ),
                                    ),
                                    _field(
                                        "Origin",
                                        dcc.Input(
                                            id="contract_origin",
                                            placeholder="Shenzhen, China",
                                            className="form-control",
                                        ),
                                    ),
                                    _field(
                                        "Destination",
                                        dcc.Input(
                                            id="contract_destination",
                                            placeholder="Kampala, Uganda",
                                            className="form-control",
                                        ),
                                    ),
                                    _field(
                                        "Expected Clearance Scope",
                                        dcc.Textarea(
                                            id="contract_clearance_scope",
                                            placeholder="Full customs clearance including IDF, port handling, duty assessment, and inland delivery",
                                            className="form-control textarea",
                                        ),
                                    ),
                                ],
                                className="form-grid",
                            ),
                            section_label(
                                "Services & Fees",
                                "Defines the clearing services, reimbursements, taxes, and payment terms agreed with the client.",
                                "lucide:receipt-text",
                            ),
                            html.Div(
                                [
                                    _field(
                                        "Services",
                                        dcc.Textarea(
                                            id="contract_services",
                                            placeholder="Services to be performed by the clearing agent",
                                            className="form-control textarea",
                                        ),
                                    ),
                                    _field(
                                        "Fees & Payment Terms",
                                        dcc.Textarea(
                                            id="contract_fees",
                                            placeholder="Fees, reimbursements, taxes, payment terms",
                                            className="form-control textarea",
                                        ),
                                    ),
                                ],
                                className="form-grid",
                            ),
                            section_label(
                                "Contract Terms",
                                "Stores the legal terms attached to the contract before preview and client signing.",
                                "lucide:file-text",
                            ),
                            _field(
                                "Attached Terms of Contract",
                                dcc.Textarea(
                                    id="contract_terms",
                                    placeholder="Concise full contract terms for the importer to review before signing",
                                    className="form-control textarea contract-terms-input",
                                    value=repository.default_contract_terms(),
                                ),
                            ),
                            html.Button("Create & Preview Contract", id="create-contract", className="btn-primary", type="button"),
                        ],
                        className="card section-card stack",
                    ),
                    html.Div(
                        [
                            html.H2("Contract Register"),
                            html.P(
                                "Search existing contracts, signature status, hashes, and importer details for follow-up.",
                                className="muted section-lead",
                            ),
                            _table_toolbar("contracts-search", "Search contracts by number, importer, email, status, signature, or fingerprint..."),
                            html.Div(id="contract-register"),
                            html.Div(id="contracts-pagination"),
                        ],
                        className="card section-card",
                    ),
                ],
                className="page-content stack",
            ),
        ]
    )


TABLE_PAGE_SIZE = 8


def _table_toolbar(search_id: str, placeholder: str):
    return html.Div(
        [
            icon("lucide:search", 15),
            dcc.Input(id=search_id, placeholder=placeholder, className="form-control table-search-input"),
        ],
        className="table-toolbar",
    )


def _matches_text(values: list, search: str | None) -> bool:
    term = (search or "").strip().lower()
    if not term:
        return True
    haystack = " ".join(str(value or "") for value in values).lower()
    return all(part in haystack for part in term.split())


def _contract_matches(contract: dict, search: str | None) -> bool:
    return _matches_text(
        [
            contract.get("contract_no"),
            contract.get("contract_hash"),
            contract.get("importer_name"),
            contract.get("importer_email"),
            contract.get("importer_phone"),
            contract.get("status"),
            contract.get("signed_by"),
            contract.get("signed_at"),
            contract.get("created_at"),
        ],
        search,
    )


def _page_rows(rows: list[dict], page: int | None) -> tuple[list[dict], int, int]:
    total_pages = max(1, ((len(rows) - 1) // TABLE_PAGE_SIZE) + 1)
    current = max(1, min(int(page or 1), total_pages))
    start = (current - 1) * TABLE_PAGE_SIZE
    return rows[start : start + TABLE_PAGE_SIZE], current, total_pages


def _pagination_controls(total_rows: int, page: int, total_pages: int | None = None):
    total_pages = total_pages or max(1, ((total_rows - 1) // TABLE_PAGE_SIZE) + 1)
    return html.Div(
        [
            html.Button("Previous", id="contracts-prev", className="btn-secondary compact", type="button", disabled=page <= 1),
            html.Span(f"Page {page} of {total_pages} | {total_rows} records", className="muted"),
            html.Button("Next", id="contracts-next", className="btn-secondary compact", type="button", disabled=page >= total_pages),
        ],
        className="table-pagination",
    )


def _contract_register(contracts: list[dict]):
    return status_table(
        ["Contract", "Importer", "Status", "Signature", "Share"],
        [
            [
                html.Div(
                    [
                        html.Strong(contract["contract_no"]),
                        html.Br(),
                        html.Small((contract.get("contract_hash") or "No fingerprint yet")[:18], className="muted"),
                    ]
                ),
                html.Div(
                    [
                        html.Strong(contract["importer_name"]),
                        html.Br(),
                        html.Small(contract.get("importer_email") or contract.get("importer_phone") or "-", className="muted"),
                    ]
                ),
                badge(contract["status"]),
                html.Div(
                    [
                        html.Strong(contract.get("signed_by") or "-"),
                        html.Br(),
                        html.Small(contract.get("signed_at") or "Pending client signature", className="muted"),
                    ]
                ),
                html.Div(
                    [
                        html.Button(
                            icon("lucide:eye", 17),
                            id={"type": "preview-contract", "id": contract["id"]},
                            className="contract-action-icon preview",
                            type="button",
                            title="Preview contract",
                            disabled=contract["status"] == "SIGNED",
                        ),
                        html.Button(
                            icon("lucide:mail", 17),
                            id={"type": "send-contract", "id": contract["id"]},
                            className="contract-action-icon email",
                            type="button",
                            title="Send or resend email OTP",
                            disabled=contract["status"] == "SIGNED",
                        ),
                        html.A(
                            icon("lucide:message-circle", 17),
                            href=repository.contract_whatsapp_link(contract["id"]),
                            target="_blank",
                            className="contract-action-icon whatsapp",
                            title="Open WhatsApp",
                        ),
                        html.A(
                            icon("lucide:link", 17),
                            href=contract.get("qr_url") or repository.contract_sign_url(contract["id"], contract.get("importer_email")),
                            target="_blank",
                            className="contract-action-icon link",
                            title="Open signing link",
                        ),
                        html.A(
                            icon("lucide:file-check-2", 17),
                            href=repository.contract_preview_url(contract["id"]),
                            target="_blank",
                            className="contract-action-icon signed-preview",
                            title="Preview signed contract",
                            style={} if contract["status"] == "SIGNED" else {"display": "none"},
                        ),
                        html.A(
                            icon("lucide:download", 17),
                            href=repository.contract_download_url(contract["id"]),
                            target="_blank",
                            className="contract-action-icon download",
                            title="Download signed contract",
                            style={} if contract["status"] == "SIGNED" else {"display": "none"},
                        ),
                    ],
                    className="contract-action-row",
                ),
            ]
            for contract in contracts
        ],
    )


@callback(
    Output("contract-register", "children"),
    Output("contracts-pagination", "children"),
    Output("contracts-page", "data"),
    Input("_pages_location", "pathname"),
    Input("auth-user", "data"),
    Input("contracts-refresh-token", "data"),
    Input("contracts-search", "value"),
    Input("contracts-prev", "n_clicks"),
    Input("contracts-next", "n_clicks"),
    State("contracts-page", "data"),
    prevent_initial_call=False,
)
def render_contract_register(pathname, user, _refresh_token, search, _prev, _next, page):
    if (pathname or "") != "/contracts":
        raise PreventUpdate
    company_id = None if (user or {}).get("role") == "SUPER_ADMIN" else (user or {}).get("company_id") or repository.DEMO_COMPANY_ID
    trigger = ctx.triggered_id
    requested_page = int(page or 1)
    if trigger == "contracts-prev":
        requested_page -= 1
    elif trigger == "contracts-next":
        requested_page += 1
    else:
        requested_page = 1
    contracts = [row for row in repository.list_contracts(company_id) if _contract_matches(row, search)]
    visible, current_page, total_pages = _page_rows(contracts, requested_page)
    return _contract_register(visible), _pagination_controls(len(contracts), current_page, total_pages), current_page


def _shipment_cards(contract: dict):
    shipment = repository.parse_shipment_details(contract.get("shipment_details"))
    labels = [
        ("Shipment Route", "shipment_route"),
        ("BL Reference", "bl_reference"),
        ("Cargo", "cargo"),
        ("Origin", "origin"),
        ("Destination", "destination"),
        ("Clearance Scope", "expected_clearance_scope"),
    ]
    return html.Div([detail_item(label, shipment.get(key)) for label, key in labels], className="detail-grid")


def _contract_preview(contract: dict):
    company_id = contract.get("company_id") or repository.DEMO_COMPANY_ID
    company = repository.get_company(company_id)
    logo_url = repository.company_logo_href(company_id)
    return html.Div(
        [
            html.Div(
                [
                    html.Img(src="/assets/zcams-logo.png", className="contract-preview-logo", alt="ZCAMS"),
                    html.Div(
                        [
                            html.P("Contract Preview", className="eyebrow"),
                            html.H2(contract.get("contract_no")),
                            html.P(company.get("name") or "Clearing & Forwarding Agent", className="muted"),
                        ]
                    ),
                    html.Img(src=logo_url, className="contract-preview-company-logo", alt="Company logo") if logo_url else None,
                ],
                className="contract-preview-header",
            ),
            html.Div(
                [
                    detail_item("Importer", contract.get("importer_name")),
                    detail_item("Registered Email", contract.get("importer_email")),
                    detail_item("WhatsApp", contract.get("importer_phone")),
                    detail_item("Status", contract.get("status")),
                ],
                className="detail-grid",
            ),
            html.H3("Shipment Details"),
            _shipment_cards(contract),
            html.H3("Services & Fees"),
            html.Div(
                [
                    html.P(contract.get("services") or "No service details supplied.", className="contract-text-block"),
                    html.P(contract.get("fees") or "No fee details supplied.", className="contract-text-block"),
                ],
                className="form-grid",
            ),
            html.H3("Attached Terms of Contract"),
            html.Div(contract.get("terms") or repository.default_contract_terms(), className="contract-terms-scroll"),
        ],
        className="contract-preview",
    )


def _send_panel(contract: dict):
    return html.Div(
        html.Div(
            [
                dcc.Store(id="contract-review-email-contract-id", data=contract.get("id")),
                html.Div(
                    [
                        html.Div(
                            [
                                html.P("Contract Preview", className="eyebrow"),
                                html.H2(f"Review {contract.get('contract_no')} before sending"),
                                html.P(
                                    "This is the developed contract the importer will open from the signing link.",
                                    className="muted",
                                ),
                            ]
                        ),
                        html.Button("x", id="contract-send-close", className="modal-close", title="Close", type="button"),
                    ],
                    className="modal-header",
                ),
                _contract_preview(contract),
                html.Div(
                    [
                        detail_item("Importer", contract.get("importer_name")),
                        detail_item("Registered Email", contract.get("importer_email")),
                        detail_item("Contract ID", contract.get("contract_no")),
                        detail_item("OTP", contract.get("otp")),
                    ],
                    className="detail-grid contract-preview-send-details",
                ),
                html.P("Send options", className="detail-label"),
                html.Div(
                    [
                        html.Button("Send / Resend Email OTP", id="contract-send-email", className="btn-primary", type="button"),
                        dcc.Checklist(
                            id="contract-attach-pdf",
                            options=[{"label": "Attach developed contract PDF", "value": "PDF"}],
                            value=["PDF"],
                            className="inline-checklist",
                        ),
                        html.A("Open WhatsApp", href=repository.contract_whatsapp_url(contract), target="_blank", className="btn-secondary"),
                        html.A("Open Signing Link", href=contract.get("qr_url"), target="_blank", className="btn-secondary"),
                    ],
                    className="row-actions contract-send-actions",
                ),
                html.Div(id="contract-modal-send-result"),
            ],
            className="invoice-modal-card stack contract-preview-modal-card",
        ),
        className="modal-backdrop contract-preview-backdrop",
    )


@callback(
    Output("contract-result", "children"),
    Output("latest-contract-id", "data"),
    Output("contract-preview-id", "data"),
    Output("contracts-refresh-token", "data"),
    Input("create-contract", "n_clicks"),
    State("contract_importer", "value"),
    State("contract_phone", "value"),
    State("contract_email", "value"),
    State("contract_shipment_route", "value"),
    State("contract_bl_reference", "value"),
    State("contract_cargo", "value"),
    State("contract_origin", "value"),
    State("contract_destination", "value"),
    State("contract_clearance_scope", "value"),
    State("contract_services", "value"),
    State("contract_fees", "value"),
    State("contract_terms", "value"),
    State("auth-user", "data"),
    State("contracts-refresh-token", "data"),
    prevent_initial_call=True,
)
def create_contract(
    _create,
    importer,
    phone,
    email,
    shipment_route,
    bl_reference,
    cargo,
    origin,
    destination,
    clearance_scope,
    services,
    fees,
    terms,
    user,
    refresh_token,
):
    if not importer or not email:
        return html.Div("Importer name and email are required.", className="notice error"), no_update, no_update, no_update
    shipment = repository.shipment_payload(
        shipment_route=shipment_route or "",
        bl_reference=bl_reference or "",
        cargo=cargo or "",
        origin=origin or "",
        destination=destination or "",
        expected_clearance_scope=clearance_scope or "",
    )
    contract = repository.create_contract(
        importer,
        phone or "",
        email or "",
        terms or repository.default_contract_terms(),
        shipment_details=shipment,
        services=services or "",
        fees=fees or "",
        company_id=(user or {}).get("company_id") or repository.DEMO_COMPANY_ID,
    )
    return (
        html.Div(
            f"Contract preview created: {contract['contract_no']}. Review it below before sending to the importer.",
            className="notice success",
        ),
        contract["id"],
        contract["id"],
        (refresh_token or 0) + 1,
    )


@callback(
    Output("contract-modal-send-result", "children"),
    Output("contracts-refresh-token", "data", allow_duplicate=True),
    Input("contract-send-email", "n_clicks"),
    State("contract-review-email-contract-id", "data"),
    State("contract-attach-pdf", "value"),
    State("contracts-refresh-token", "data"),
    prevent_initial_call=True,
)
def contract_review_email_send(email_clicks, contract_id, attach_pdf_values, refresh_token):
    if not email_clicks or not contract_id:
        raise PreventUpdate
    delivery = repository.send_contract_review_email(
        contract_id,
        attach_pdf="PDF" in (attach_pdf_values or []),
    )
    return _contract_email_feedback(delivery), (refresh_token or 0) + 1


@callback(
    Output("contract-preview-id", "data", allow_duplicate=True),
    Output("latest-contract-id", "data", allow_duplicate=True),
    Output("contract-send-result", "children", allow_duplicate=True),
    Input({"type": "preview-contract", "id": ALL}, "n_clicks"),
    State({"type": "preview-contract", "id": ALL}, "id"),
    prevent_initial_call=True,
)
def preview_contract_from_row(row_clicks, row_ids):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or trigger.get("type") != "preview-contract":
        raise PreventUpdate
    clicked = next(
        (clicks for clicks, row_id in zip(row_clicks or [], row_ids or []) if row_id.get("id") == trigger.get("id")),
        None,
    )
    if not clicked:
        raise PreventUpdate
    contract = repository.get_contract(trigger.get("id"))
    if not contract:
        raise PreventUpdate
    return contract["id"], contract["id"], None


@callback(
    Output("contract-send-result", "children", allow_duplicate=True),
    Output("contracts-refresh-token", "data", allow_duplicate=True),
    Input({"type": "send-contract", "id": ALL}, "n_clicks"),
    State({"type": "send-contract", "id": ALL}, "id"),
    State("contracts-refresh-token", "data"),
    prevent_initial_call=True,
)
def send_contract_from_row(row_clicks, row_ids, refresh_token):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or trigger.get("type") != "send-contract":
        raise PreventUpdate
    clicked = next(
        (clicks for clicks, row_id in zip(row_clicks or [], row_ids or []) if row_id.get("id") == trigger.get("id")),
        None,
    )
    if not clicked:
        raise PreventUpdate
    return _send_contract_feedback(trigger.get("id"), refresh_token, attach_pdf=False)


def _send_contract_feedback(contract_id, refresh_token, *, attach_pdf: bool):
    delivery = repository.send_contract_to_importer(contract_id, attach_pdf=attach_pdf)
    return _contract_email_feedback(delivery), (refresh_token or 0) + 1


def _contract_email_feedback(delivery):
    email_result = delivery["email"]
    mode = email_result.get("mode", "mock")
    if email_result.get("sent"):
        attachment_note = " with the developed contract PDF attached" if delivery.get("attached_pdf") else ""
        message = f"Email sent with signing link, Contract ID, and OTP{attachment_note}."
        css = "notice success"
    else:
        reason = email_result.get("reason") or "email provider is not configured"
        status = email_result.get("status_code")
        prefix = f"{mode} {status}" if status else mode
        message = f"Email not sent automatically ({prefix}: {reason}). Use WhatsApp or the signing link shown on the contract row."
        css = "notice error"
    return html.Div(
        [
            html.Span(message),
            html.A("Open WhatsApp with OTP", href=delivery["whatsapp"], target="_blank", className="btn-secondary"),
        ],
        className=css,
    )


@callback(
    Output("contract-preview-modal-layer", "children"),
    Input("contract-preview-id", "data"),
    prevent_initial_call=False,
)
def render_contract_preview_modal(contract_id):
    if not contract_id:
        return None
    contract = repository.get_contract(contract_id)
    if not contract:
        return None
    return _send_panel(contract)


@callback(
    Output("contract-preview-id", "data", allow_duplicate=True),
    Input("contract-send-close", "n_clicks"),
    prevent_initial_call=True,
)
def close_send_panel(_n_clicks):
    return None
