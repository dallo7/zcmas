from urllib.parse import parse_qs

from dash import Input, Output, State, callback, dcc, html, no_update, register_page

from components.ui import detail_item
from services import repository


register_page(__name__, path="/contract-sign", name="Sign Contract")


def layout(**_kwargs):
    return html.Div(
        [
            dcc.Store(id="sign-contract-internal-id"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Img(src="/assets/zcams-logo.png", className="contract-preview-logo", alt="ZCAMS"),
                            html.Div(
                                [
                                    html.P("Zambia Customs Agent Management System", className="eyebrow"),
                                    html.H1("Secure Contract Signature"),
                                    html.P(
                                        "Verify your registered email, Contract ID, and OTP before signing.",
                                        className="muted",
                                    ),
                                ]
                            ),
                        ],
                        className="public-contract-header",
                    ),
                    html.Div(id="sign-contract-load-result"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2("Contract To Review"),
                                    html.P(
                                        "Read the contract details, shipment scope, services, fees, and terms before signing.",
                                        className="muted section-lead",
                                    ),
                                    html.Div(id="sign-contract-summary"),
                                ],
                                className="card section-card stack",
                            ),
                            html.Div(
                                [
                                    html.H2("Verify & Sign"),
                                    html.P(
                                        "Enter the registered email, contract ID, OTP, and signature confirmation to complete the secure signing step.",
                                        className="muted section-lead",
                                    ),
                                    html.Div(
                                        [
                                            dcc.Input(
                                                id="sign-contract-email",
                                                placeholder="Registered email address",
                                                type="email",
                                                className="form-control",
                                            ),
                                            dcc.Input(
                                                id="sign-contract-no",
                                                placeholder="Contract ID e.g. CTR-2026-12345",
                                                className="form-control",
                                            ),
                                            dcc.Input(
                                                id="sign-contract-otp",
                                                placeholder="6-digit OTP",
                                                maxLength=6,
                                                className="form-control",
                                            ),
                                        ],
                                        className="form-grid",
                                    ),
                                    dcc.Textarea(
                                        id="sign-contract-drawn",
                                        placeholder="Draw/write your signature here, or attach a signature image below.",
                                        className="form-control textarea calligraphic-signature-input",
                                    ),
                                    dcc.Upload(
                                        id="sign-contract-upload",
                                        children=html.Div(["Attach signature image or PDF"]),
                                        className="bl-upload-button signature-upload",
                                        multiple=False,
                                    ),
                                    dcc.Input(
                                        id="sign-contract-name",
                                        placeholder="Type your full name to confirm",
                                        className="form-control",
                                    ),
                                    html.Div(id="signature-preview", className="signature-preview"),
                                    html.Button("Sign Contract", id="sign-contract-submit", className="btn-primary"),
                                    html.Div(id="sign-contract-result"),
                                ],
                                className="card section-card stack",
                            ),
                        ],
                        className="two-column",
                    ),
                ],
                className="public-contract-shell",
            ),
        ],
        className="public-page contract-sign-page",
    )


def _query_value(search: str | None, key: str) -> str:
    values = parse_qs((search or "").lstrip("?")).get(key) or [""]
    return values[0]


def _contract_summary(contract: dict | None):
    if not contract:
        return html.Div(
            "Open this page from the signing link sent by your clearing agent, or enter your Contract ID manually.",
            className="notice",
        )
    company_id = contract.get("company_id") or repository.DEMO_COMPANY_ID
    company = repository.get_company(company_id)
    logo_url = repository.company_logo_href(company_id)
    shipment = repository.parse_shipment_details(contract.get("shipment_details"))
    return html.Div(
        [
            html.Div(
                [
                    html.Img(src="/assets/zcams-logo.png", className="contract-preview-logo", alt="ZCAMS"),
                    html.Div(
                        [
                            html.P("Contract Signature Request", className="eyebrow"),
                            html.H2(company.get("name") or "Clearing & Forwarding Agent"),
                            html.P("Review the attached terms before signing.", className="muted"),
                        ]
                    ),
                    html.Img(src=logo_url, className="contract-preview-company-logo", alt="Company logo") if logo_url else None,
                ],
                className="contract-preview-header",
            ),
            html.Div(
                [
                    detail_item("Importer", contract.get("importer_name")),
                    detail_item("Contract ID", contract.get("contract_no")),
                    detail_item("Registered Email", contract.get("importer_email")),
                    detail_item("Status", contract.get("status")),
                ],
                className="detail-grid",
            ),
            html.H3("Shipment Details"),
            html.P("Shipment route, BL reference, cargo, origin, destination, and clearance scope attached to this agreement.", className="muted section-label-copy"),
            html.Div(
                [
                    detail_item("Shipment Route", shipment.get("shipment_route")),
                    detail_item("BL Reference", shipment.get("bl_reference")),
                    detail_item("Cargo", shipment.get("cargo")),
                    detail_item("Origin", shipment.get("origin")),
                    detail_item("Destination", shipment.get("destination")),
                    detail_item("Clearance Scope", shipment.get("expected_clearance_scope")),
                ],
                className="detail-grid",
            ),
            html.H3("Services & Fees"),
            html.P("Services to be performed and the fees or payment terms accepted by the signer.", className="muted section-label-copy"),
            html.P(contract.get("services") or "No service details supplied.", className="contract-text-block"),
            html.P(contract.get("fees") or "No fee details supplied.", className="contract-text-block"),
            html.H3("Attached Terms of Contract"),
            html.P("Legal terms that become part of the signed contract fingerprint.", className="muted section-label-copy"),
            html.Div(contract.get("terms") or repository.default_contract_terms(), className="contract-terms-scroll"),
            html.Div(
                "After signing, ZCAMS stores a SHA-256 fingerprint of the complete signed contract data. "
                "Any later change to the contract details or signature data creates a different fingerprint.",
                className="notice",
            ),
        ],
        className="stack",
    )


@callback(
    Output("sign-contract-internal-id", "data"),
    Output("sign-contract-summary", "children"),
    Output("sign-contract-email", "value"),
    Output("sign-contract-no", "value"),
    Input("_pages_location", "search"),
    prevent_initial_call=False,
)
def load_contract_for_signature(search):
    contract_id = _query_value(search, "contract")
    email = _query_value(search, "email")
    contract = repository.get_contract(contract_id) if contract_id else None
    return (
        contract.get("id") if contract else None,
        _contract_summary(contract),
        email or (contract.get("importer_email") if contract else ""),
        contract.get("contract_no") if contract else "",
    )


@callback(
    Output("signature-preview", "children"),
    Input("sign-contract-drawn", "value"),
    Input("sign-contract-name", "value"),
    prevent_initial_call=False,
)
def render_signature_preview(signature_text, typed_name):
    signature = (signature_text or typed_name or "").strip()
    if not signature:
        return "Your written signature preview will appear here."
    return html.Div(signature, className="calligraphic-signature")


@callback(
    Output("sign-contract-result", "children"),
    Output("sign-contract-summary", "children", allow_duplicate=True),
    Input("sign-contract-submit", "n_clicks"),
    State("sign-contract-internal-id", "data"),
    State("sign-contract-email", "value"),
    State("sign-contract-no", "value"),
    State("sign-contract-otp", "value"),
    State("sign-contract-name", "value"),
    State("sign-contract-drawn", "value"),
    State("sign-contract-upload", "contents"),
    State("sign-contract-upload", "filename"),
    prevent_initial_call=True,
)
def sign_contract(
    _n_clicks,
    internal_contract_id,
    email,
    contract_no,
    otp,
    signature_name,
    signature_text,
    upload_contents,
    upload_filename,
):
    try:
        contract = repository.sign_contract_with_otp(
            contract_no=contract_no or "",
            email=email or "",
            otp=otp or "",
            signature_name=signature_name or "",
            signature_text=signature_text or signature_name or "",
            signature_file_contents=upload_contents,
            signature_file_name=upload_filename,
            contract_id=internal_contract_id,
        )
    except ValueError as exc:
        return html.Div(str(exc), className="notice error"), no_update
    return (
        html.Div(
            [
                html.Strong("Contract signed successfully."),
                html.Br(),
                html.Small(f"Hash fingerprint: {contract.get('contract_hash')}"),
            ],
            className="notice success",
        ),
        _contract_summary(contract),
    )
