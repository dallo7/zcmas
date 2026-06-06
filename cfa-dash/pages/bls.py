import base64
import binascii
from pathlib import Path

import dash_ag_grid as dag
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate

from components.icons import icon
from components.layout import header, section_label
from components.workflow import shortcut_chip
from services import ocr
from services import repository
from services.db import UPLOAD_DIR
from services.gn83 import all_category_options, is_gn83_exempt, lookup_fee, unit_label
from services.repository import BL_CANCEL_REASONS, BlNumberConflict


register_page(__name__, path="/bls", name="BLs")

def _capture_field(label: str, control, *, span: int = 1) -> html.Div:
    """Label above control for aligned BL capture grid."""
    style = {"gridColumn": f"span {span}"} if span > 1 else None
    return html.Div(
        [html.Label(label), control],
        className="form-field",
        style=style,
    )


UPLOAD_PROGRESS_STAGES = [
    (20, "Uploading document…"),
    (55, "Extracting BL fields…"),
    (100, "OCR complete"),
]


def _company_registration_defaults(user: dict | None = None) -> dict:
    company_id = (user or {}).get("company_id") or repository.DEMO_COMPANY_ID
    company = repository.get_company(company_id)
    return {
        "company_name": company.get("name") or "",
        "company_tpin": company.get("tpin") or "",
        "zra_licence": company.get("zra_licence") or "",
    }


def _gn83_dynamic_values(route_type, transport_mode, category, no_containers, gross_weight) -> tuple[str, float]:
    selected_category = category or "MOTOR_VEHICLE"
    return (
        unit_label(selected_category),
        lookup_fee(
            route_type or "Import",
            transport_mode or "Sea",
            selected_category,
            no_containers=no_containers,
            gross_weight=gross_weight,
        ),
    )


def layout(**_kwargs):
    bls = repository.list_bls()
    return html.Div(
        [
            dcc.Store(id="bl-uploaded-file"),
            dcc.Store(id="bl-extracted-data"),
            dcc.Store(id="bl-upload-pending"),
            dcc.Store(id="bl-duplicate-conflict"),
            dcc.Store(id="bl-edit-id"),
            dcc.Interval(id="bl-upload-interval", interval=350, disabled=True, n_intervals=0),
            _save_confirm_modal(),
            header(
                "Bill of Lading Management",
                actions=[
                    dcc.Link([icon("lucide:file-star", 14), "GN 83 Schedule"], href="/gn83", className="btn-secondary"),
                    dcc.Link([icon("lucide:file-check-2", 14), "Reviewed BL"], href="/reviewed-bl#active-reviewed-bls", className="btn-secondary"),
                ],
                help_text="Classify the customs document, enter or review extracted BL data, then save it for Z-SAD review.",
                pathname="/bls",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Span(icon("lucide:ship-wheel", 18), className="bl-capture-eyebrow-icon"),
                                            html.Span("ZCAMS Document Capture", className="bl-capture-eyebrow"),
                                        ],
                                        className="bl-capture-eyebrow-row",
                                    ),
                                    html.H2("Upload / Capture BL"),
                                    html.P(
                                        "Upload a source document or capture verified customs values. ZCAMS prepares the BL for Z-SAD generation and full settlement.",
                                        className="muted section-lead",
                                    ),
                                ],
                                className="bl-capture-heading",
                            ),
                            html.Div(
                                [
                                    dcc.Upload(
                                        id="bl-upload",
                                        children=html.Div(
                                            [
                                                icon("lucide:cloud-upload", 24),
                                                html.Strong("Upload BL / AWB document"),
                                                html.Span("PDF, scanned image, Word document, or image file"),
                                            ]
                                        ),
                                        className="bl-upload-button btn-primary",
                                        multiple=False,
                                        accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.doc,.docx",
                                    ),
                                    html.Div(
                                        [
                                            html.Strong("AI-assisted extraction"),
                                            html.Span("Review every field before saving. Z-SAD is generated only after confirmation."),
                                        ],
                                        className="bl-upload-note",
                                    ),
                                ],
                                className="bl-upload-hero",
                            ),
                            html.Div(id="bl-upload-progress"),
                            html.Div(id="bl-review-prompt"),
                            html.Div(id="bl-ocr-result"),
                            html.Div(
                                [
                                    section_label(
                                        "BL Capture Fields",
                                        "Enter or review extracted values before saving the BL for Z-SAD review.",
                                        "lucide:form-input",
                                    ),
                                    html.Div(
                                        [
                                    _capture_field(
                                        "BL Number",
                                        dcc.Input(id="bl_number", placeholder="e.g. MAEU0662766336", className="form-control"),
                                    ),
                                    _capture_field(
                                        "Document type",
                                        dcc.Dropdown(
                                            id="doc_type",
                                            value="Bill of Lading",
                                            options=[
                                                {"label": v, "value": v}
                                                for v in ["Bill of Lading", "Air Waybill", "Road Consignment", "Export"]
                                            ],
                                            className="zcams-dropdown",
                                            clearable=False,
                                        ),
                                    ),
                                    _capture_field(
                                        "Route",
                                        dcc.Dropdown(
                                            id="route_type",
                                            value="Import",
                                            options=[{"label": v, "value": v} for v in ["Import", "Export", "Transit"]],
                                            className="zcams-dropdown",
                                            clearable=False,
                                        ),
                                    ),
                                    _capture_field(
                                        "Transport mode",
                                        dcc.Dropdown(
                                            id="transport_mode",
                                            value="Sea",
                                            options=[{"label": v, "value": v} for v in ["Sea", "Road", "Rail", "Air"]],
                                            className="zcams-dropdown",
                                            clearable=False,
                                        ),
                                    ),
                                    _capture_field(
                                        "ZRA regime",
                                        dcc.Dropdown(
                                            id="zra_regime",
                                            value="IM4 Home Use",
                                            options=[
                                                {"label": v, "value": v}
                                                for v in [
                                                    "IM4 Home Use",
                                                    "IM5 Temporary Import",
                                                    "IM6 Re-importation",
                                                    "IM7 Warehousing",
                                                    "IM9 Other",
                                                ]
                                            ],
                                            className="zcams-dropdown",
                                            clearable=False,
                                        ),
                                    ),
                                    _capture_field(
                                        "Consignee",
                                        dcc.Input(id="consignee_name", placeholder="Consignee name", className="form-control"),
                                    ),
                                    _capture_field(
                                        "Company name",
                                        dcc.Input(id="company_name", placeholder="Importer/exporter legal name", className="form-control"),
                                    ),
                                    _capture_field(
                                        "Consignee TIN",
                                        dcc.Input(id="consignee_tin", placeholder="TPIN / TIN", className="form-control"),
                                    ),
                                    _capture_field(
                                        "Consignor TIN",
                                        dcc.Input(id="consignor_tin", placeholder="Shipper / consignor TIN", className="form-control"),
                                    ),
                                    _capture_field(
                                        "Agent license",
                                        dcc.Input(id="agent_license", placeholder="ZRA agent registration", className="form-control"),
                                    ),
                                    _capture_field(
                                        "Company TIN / TPIN",
                                        dcc.Input(id="declarant_number", placeholder="Company TIN / TPIN", className="form-control"),
                                    ),
                                    _capture_field(
                                        "Consignment value",
                                        dcc.Input(id="consignment_value", placeholder="Declared value", type="number", className="form-control"),
                                    ),
                                    _capture_field(
                                        "Origin",
                                        dcc.Input(id="origin", placeholder="Origin port or city", className="form-control"),
                                    ),
                                    _capture_field(
                                        "Destination",
                                        dcc.Input(id="destination", placeholder="Destination", className="form-control"),
                                    ),
                                    _capture_field(
                                        "No. of containers",
                                        dcc.Input(
                                            id="no_containers",
                                            placeholder="0 for loose cargo",
                                            type="number",
                                            min=0,
                                            className="form-control",
                                        ),
                                    ),
                                    _capture_field(
                                        "Gross weight (MT)",
                                        dcc.Input(id="gross_weight", placeholder="Metric tonnes", type="number", className="form-control"),
                                    ),
                                    _capture_field(
                                        "Cargo description",
                                        dcc.Input(id="cargo_description", placeholder="Description of goods", className="form-control"),
                                        span=2,
                                    ),
                                    _capture_field(
                                        "GN 83 category",
                                        dcc.Dropdown(
                                            id="gn83_category",
                                            options=all_category_options(),
                                            value="MOTOR_VEHICLE",
                                            className="zcams-dropdown",
                                            clearable=False,
                                        ),
                                        span=2,
                                    ),
                                    _capture_field(
                                        "GN 83 unit",
                                        dcc.Input(id="gn83_unit", placeholder="Container / AWB / BL / MT", className="form-control"),
                                    ),
                                    _capture_field(
                                        "GN 83 fee USD",
                                        dcc.Input(id="gn83_fee_usd", placeholder="Standard minimum fee", type="number", className="form-control"),
                                    ),
                                        ],
                                        className="bl-capture-grid",
                                        id="bl-capture-section",
                                    ),
                                    html.Div(
                                        [
                                            html.Button("Save BL", id="save-bl", className="btn-primary", type="button"),
                                        ],
                                        className="row-actions wrap bl-form-actions",
                                    ),
                                ],
                                className="bl-capture-body",
                            ),
                            html.Div(id="bl-result"),
                            html.Div(
                                id="bl-post-save-bar",
                                style={"display": "none"},
                                className="next-step-banner",
                                children=[
                                    html.Div(
                                        [
                                            html.Button(
                                                "Complete Full Settlement invoice",
                                                id="bl-request-invoice",
                                                className="btn-primary",
                                                type="button",
                                                n_clicks=0,
                                            ),
                                            dcc.Link("GN 83 lookup", href="/gn83", className="btn-secondary"),
                                        ],
                                        className="next-step-actions",
                                    ),
                                ],
                            ),
                        ],
                        className="card section-card bl-capture-card",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2("Uploaded BLs"),
                                    shortcut_chip("Next: request invoice", "/reviewed-bl#active-reviewed-bls", "lucide:receipt"),
                                ],
                                className="section-heading-row",
                            ),
                            section_label(
                                "Saved BL Register",
                                "Lists BLs already captured in ZCAMS for audit and follow-up after Z-SAD issuance.",
                                "lucide:table-properties",
                            ),
                            html.Div(id="bl-table", children=_bl_table(bls)),
                        ],
                        className="card section-card",
                    ),
                ],
                className="page-content stack",
            ),
            _detach_modal(),
        ]
    )


def _progress_bar(percent: int, label: str) -> html.Div:
    pct = max(0, min(100, int(percent)))
    return html.Div(
        [
            html.Div(
                [
                    html.Div(className="bl-progress-fill", style={"width": f"{pct}%"}),
                ],
                className="bl-progress-track",
                role="progressbar",
                **{"aria-valuenow": pct, "aria-valuemin": 0, "aria-valuemax": 100},
            ),
            html.P(label, className="bl-progress-label"),
        ],
        className="bl-progress-wrap",
    )


def _review_prompt_banner() -> html.Div:
    return html.Div(
        [
            icon("lucide:clipboard-check", 18),
            html.Div(
                [
                    html.Strong("Prepare to review the uploaded document"),
                    html.P(
                        "Compare the uploaded file against the extracted BL fields below, "
                        "correct any OCR gaps, and apply the correct GN 83 enforcement before saving."
                    ),
                ],
                className="bl-review-prompt-copy",
            ),
        ],
        className="notice bl-review-prompt",
    )


def _save_confirm_modal() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H2("Confirm BL before Z-SAD"),
                            html.Button("×", id="bl-save-confirm-close", className="modal-close", title="Close", type="button"),
                        ],
                        className="modal-header",
                    ),
                    html.Div(id="bl-save-confirm-body", className="detach-modal-body"),
                    html.Div(
                        [
                            html.Button("Edit Again", id="bl-save-edit-again", className="btn-secondary", type="button"),
                            html.Button(
                                "Yes, Save and Generate Z-SAD",
                                id="bl-save-confirm-submit",
                                className="btn-primary",
                                type="button",
                            ),
                        ],
                        className="modal-actions",
                    ),
                ],
                className="invoice-modal-card detach-modal-card",
            )
        ],
        id="bl-save-confirm-modal",
        className="modal-backdrop is-hidden",
    )


def _detach_modal() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H2("Detach Z-SAD & cancel previous BL"),
                            html.Button("×", id="bl-detach-close", className="modal-close", title="Close", type="button"),
                        ],
                        className="modal-header",
                    ),
                    html.Div(id="bl-detach-body", className="detach-modal-body"),
                            html.Div(
                                [
                                    html.Label("Reason for cancellation"),
                                    dcc.Dropdown(
                                        id="bl-cancel-reason",
                                        options=[{"label": r, "value": r} for r in BL_CANCEL_REASONS],
                                        placeholder="Select a reason",
                                        className="form-control",
                                    ),
                                    html.Div(
                                        [
                                            html.Label("Other — state the reason"),
                                            dcc.Textarea(
                                                id="bl-cancel-reason-detail",
                                                placeholder="Brief explanation",
                                                className="form-control textarea",
                                            ),
                                        ],
                                        id="bl-cancel-other-wrap",
                                        className="stack compact",
                                        style={"display": "none"},
                                    ),
                                    html.Div(
                                        [
                                            html.Button("Cancel", id="bl-detach-close-secondary", className="btn-secondary", type="button"),
                                            html.Button(
                                                "Detach Z-SAD & cancel record",
                                                id="bl-detach-submit",
                                                className="btn-primary",
                                                type="button",
                                            ),
                                        ],
                                        className="modal-actions",
                                    ),
                                ],
                                id="bl-detach-form",
                                className="stack",
                            ),
                ],
                className="invoice-modal-card detach-modal-card",
            )
        ],
        id="bl-detach-modal",
        className="modal-backdrop is-hidden",
    )


def _bl_cancel_details(bl: dict) -> str:
    if (bl.get("status") or "") != "CANCELLED":
        return "-"
    who = bl.get("cancelled_by_name") or repository.get_user_display(bl.get("cancelled_by"))
    when = (bl.get("cancelled_at") or "-").replace("T", " ")[:19]
    reason = bl.get("cancel_reason") or "-"
    if reason == "Other" and bl.get("cancel_reason_detail"):
        reason = f"Other: {bl['cancel_reason_detail']}"
    return f"{who} | {reason} | {when}"


def _bl_grid_rows(bls: list[dict]) -> list[dict]:
    return [
        {
            "id": bl.get("id"),
            "bl_number": bl.get("display_bl_number") or bl.get("bl_number") or "-",
            "route": bl.get("route_type") or "-",
            "transport": bl.get("transport_mode") or "-",
            "consignee": bl.get("consignee_name") or "-",
            "status": (bl.get("status") or "-").replace("_", " ").title(),
            "raw_status": bl.get("status") or "",
            "can_edit": (bl.get("status") or "") == "UPLOADED",
            "can_edit_label": "Yes" if (bl.get("status") or "") == "UPLOADED" else "Locked",
            "who": _bl_cancel_details(bl),
        }
        for bl in bls
    ]


def _bl_table(bls):
    return dag.AgGrid(
        id="uploaded-bls-grid",
        columnDefs=[
            {
                "field": "bl_number",
                "headerName": "BL Number",
                "minWidth": 260,
                "flex": 2,
                "pinned": "left",
                "checkboxSelection": True,
                "headerCheckboxSelection": True,
            },
            {"field": "route", "headerName": "Route", "minWidth": 120, "flex": 1},
            {"field": "transport", "headerName": "Transport", "minWidth": 130, "flex": 1},
            {"field": "consignee", "headerName": "Consignee", "minWidth": 220, "flex": 1.4},
            {"field": "status", "headerName": "Status", "minWidth": 170, "flex": 1},
            {
                "field": "can_edit_label",
                "headerName": "Amendable",
                "minWidth": 130,
                "flex": 0.8,
            },
            {"field": "who", "headerName": "Who / Action", "minWidth": 240, "flex": 1.3},
        ],
        rowData=_bl_grid_rows(bls),
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
            "paginationPageSize": 8,
            "animateRows": True,
            "domLayout": "autoHeight",
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
            "rowSelection": "single",
            "rowMultiSelectWithClick": False,
            "suppressRowClickSelection": False,
            "overlayNoRowsTemplate": "<span class='muted'>No BL records yet.</span>",
        },
        rowClassRules={
            "bl-grid-cancelled-row": "params.data.raw_status == 'CANCELLED'",
            "bl-grid-reviewed-row": "params.data.raw_status == 'REVIEWED'",
            "bl-grid-uploaded-row": "params.data.raw_status == 'UPLOADED'",
        },
        className="ag-theme-alpine zcams-ag-grid bls-ag-grid",
    )


def _duplicate_notice(conflict: dict) -> html.Div:
    zsad = conflict.get("z_sad_number") or "issued"
    bl_no = repository.display_bl_number(conflict)
    return html.Div(
        [
            html.Strong(f"Duplicate BL number: {bl_no}"),
            html.P(
                "This BL was already registered for your company and a Z-SAD was generated. "
                "Detach the Z-SAD from the previous record to cancel it and re-use this BL number."
            ),
            html.P(f"Active Z-SAD on file: {zsad}.", className="muted"),
            html.Button(
                "Detach Z-SAD & cancel previous record",
                id="bl-open-detach",
                className="btn-secondary",
                type="button",
            ),
        ],
        className="notice error stack compact",
    )


_DETACH_FORM_VISIBLE: dict = {}
_DETACH_FORM_HIDDEN = {"display": "none"}


def _detach_body(conflict: dict) -> list:
    bl_no = repository.display_bl_number(conflict)
    zsad = conflict.get("z_sad_number") or "-"
    return [
        html.P(
            f"BL {bl_no} will be marked Cancelled. Z-SAD {zsad} will be retired and any open invoices cancelled. "
            "After confirmation you can upload and save this BL number again.",
            className="section-lead",
        ),
        html.Ul(
            [
                html.Li("The previous record stays in the audit trail as Cancelled."),
                html.Li("Cargo-released BLs cannot be cancelled."),
                html.Li("Select a cancellation reason before confirming."),
            ],
            className="detach-checklist",
        ),
    ]


def _detach_success_body(conflict: dict) -> html.Div:
    bl_no = repository.display_bl_number(conflict)
    zsad = conflict.get("z_sad_number") or "-"
    return html.Div(
        [
            html.Div(
                [
                    html.Strong("Detach successful"),
                    html.P(
                        f"BL {bl_no} has been cancelled and Z-SAD {zsad} retired. "
                        "Any open invoices were cancelled. You can now save a new upload with the same BL number.",
                        className="section-lead",
                    ),
                ],
                className="notice success",
            ),
        ],
        className="stack compact",
    )


@callback(
    Output("bl-upload-pending", "data"),
    Output("bl-upload-interval", "disabled"),
    Output("bl-upload-interval", "n_intervals"),
    Output("bl-upload-progress", "children"),
    Output("bl-review-prompt", "children"),
    Output("bl-ocr-result", "children", allow_duplicate=True),
    Output("bl-uploaded-file", "data"),
    Output("bl-extracted-data", "data"),
    Output("bl_number", "value"),
    Output("doc_type", "value"),
    Output("route_type", "value"),
    Output("transport_mode", "value"),
    Output("zra_regime", "value"),
    Output("consignee_name", "value"),
    Output("company_name", "value"),
    Output("consignee_tin", "value"),
    Output("consignor_tin", "value"),
    Output("agent_license", "value"),
    Output("declarant_number", "value"),
    Output("consignment_value", "value"),
    Output("origin", "value"),
    Output("destination", "value"),
    Output("no_containers", "value"),
    Output("gross_weight", "value"),
    Output("cargo_description", "value"),
    Output("gn83_category", "value"),
    Output("gn83_unit", "value"),
    Output("gn83_fee_usd", "value"),
    Input("bl-upload", "contents"),
    State("bl-upload", "filename"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def queue_bl_upload(contents, filename, user=None):
    if not contents:
        raise PreventUpdate
    try:
        file_path = save_uploaded_bl(contents, filename)
    except ValueError as exc:
        return (
            None,
            True,
            0,
            html.Div(str(exc), className="notice error"),
            None,
            None,
            None,
            None,
            *[None] * 20,
        )

    try:
        extracted = ocr.extract_bl_fields(str(file_path))
    except ValueError as exc:
        return (
            None,
            True,
            0,
            html.Div(str(exc), className="notice error"),
            None,
            None,
            None,
            None,
            *[None] * 20,
        )

    mode = extracted.get("ocr_mode", "unknown")
    provider = extracted.get("ocr_provider", "ocr")
    gn83_hint = extracted.get("gn83_category")
    company_defaults = _company_registration_defaults(user)
    message = html.Div(
        [
            html.Strong(f"OCR extracted draft BL values using {provider} ({mode})."),
            html.P("Review and correct the form before saving. Z-SAD will be generated after you save."),
            html.P(f"Suggested GN 83 category: {gn83_hint}.", className="muted") if gn83_hint else None,
            html.P(extracted.get("ocr_error"), className="muted") if extracted.get("ocr_error") else None,
        ],
        className="notice success" if mode != "fallback_demo" else "notice",
    )
    done_pct, done_label = UPLOAD_PROGRESS_STAGES[-1]
    return (
        {"path": str(file_path), "filename": filename, "ocr_done": True},
        True,
        0,
        _progress_bar(done_pct, done_label),
        _review_prompt_banner(),
        message,
        {"path": str(file_path), "filename": filename},
        extracted,
        extracted.get("bl_number"),
        extracted.get("doc_type", "Bill of Lading"),
        extracted.get("route_type", "Import"),
        extracted.get("transport_mode", "Sea"),
        extracted.get("zra_regime", "IM4 Home Use"),
        extracted.get("consignee_name"),
        company_defaults["company_name"],
        extracted.get("consignee_tin"),
        extracted.get("consignor_tin"),
        extracted.get("agent_license") or extracted.get("agentLicense"),
        company_defaults["company_tpin"],
        extracted.get("consignment_value"),
        extracted.get("origin"),
        extracted.get("destination"),
        extracted.get("no_containers"),
        extracted.get("gross_weight"),
        extracted.get("cargo_description"),
        extracted.get("gn83_category", "MOTOR_VEHICLE"),
        extracted.get("gn83_unit"),
        extracted.get("gn83_fee_usd"),
    )


@callback(
    Output("company_name", "value", allow_duplicate=True),
    Output("declarant_number", "value", allow_duplicate=True),
    Input("_pages_location", "pathname"),
    Input("auth-user", "data"),
    prevent_initial_call=True,
)
def populate_company_registration_fields(pathname, user):
    if (pathname or "") != "/bls":
        raise PreventUpdate
    defaults = _company_registration_defaults(user)
    return defaults["company_name"], defaults["company_tpin"]


@callback(
    Output("gn83_unit", "value", allow_duplicate=True),
    Output("gn83_fee_usd", "value", allow_duplicate=True),
    Input("route_type", "value"),
    Input("transport_mode", "value"),
    Input("gn83_category", "value"),
    Input("no_containers", "value"),
    Input("gross_weight", "value"),
    prevent_initial_call=True,
)
def recalculate_gn83_capture_fee(route_type, transport_mode, category, no_containers, gross_weight):
    return _gn83_dynamic_values(route_type, transport_mode, category, no_containers, gross_weight)


@callback(
    Output("bl-cancel-other-wrap", "style"),
    Input("bl-cancel-reason", "value"),
)
def toggle_other_reason(reason):
    if reason == "Other":
        return {"display": "grid"}
    return {"display": "none"}


@callback(
    Output("bl-duplicate-conflict", "data"),
    Output("bl-detach-modal", "className"),
    Output("bl-detach-body", "children"),
    Output("bl-detach-form", "style"),
    Output("bl-cancel-reason", "value", allow_duplicate=True),
    Output("bl-cancel-reason-detail", "value", allow_duplicate=True),
    Input("bl-open-detach", "n_clicks"),
    Input("bl-detach-close", "n_clicks"),
    Input("bl-detach-close-secondary", "n_clicks"),
    State("bl-duplicate-conflict", "data"),
    prevent_initial_call=True,
)
def toggle_detach_modal(open_clicks, close_clicks, close2_clicks, conflict):
    trigger = ctx.triggered_id
    if trigger in {"bl-detach-close", "bl-detach-close-secondary"}:
        return None, "modal-backdrop is-hidden", None, _DETACH_FORM_VISIBLE, None, None
    if not conflict:
        raise PreventUpdate
    return conflict, "modal-backdrop", _detach_body(conflict), _DETACH_FORM_VISIBLE, no_update, no_update


@callback(
    Output("bl-result", "children", allow_duplicate=True),
    Output("bl-table", "children", allow_duplicate=True),
    Output("bl-duplicate-conflict", "data", allow_duplicate=True),
    Output("bl-detach-modal", "className", allow_duplicate=True),
    Output("bl-detach-body", "children", allow_duplicate=True),
    Output("bl-detach-form", "style", allow_duplicate=True),
    Output("bl-cancel-reason", "value"),
    Output("bl-cancel-reason-detail", "value"),
    Input("bl-detach-submit", "n_clicks"),
    State("bl-duplicate-conflict", "data"),
    State("bl-cancel-reason", "value"),
    State("bl-cancel-reason-detail", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def submit_detach_cancel(_clicks, conflict, reason, reason_detail, user):
    if not conflict:
        raise PreventUpdate
    company_id = (user or {}).get("company_id") or repository.DEMO_COMPANY_ID
    cancelled_by = (user or {}).get("id") or repository.DEMO_USER_ID
    try:
        repository.cancel_bl_for_reupload(
            conflict["id"],
            reason or "",
            reason_detail=reason_detail,
            cancelled_by=cancelled_by,
            company_id=company_id,
        )
    except ValueError as exc:
        return (
            html.Div(str(exc), className="notice error"),
            _bl_table(repository.list_bls(company_id)),
            conflict,
            "modal-backdrop",
            _detach_body(conflict),
            _DETACH_FORM_VISIBLE,
            reason,
            reason_detail,
        )
    bl_no = repository.display_bl_number(conflict)
    notice = html.Div(
        [
            html.Strong(f"Previous BL {bl_no} cancelled."),
            html.P("You can now save a new upload with the same BL number."),
        ],
        className="notice success",
    )
    return (
        notice,
        _bl_table(repository.list_bls(company_id)),
        None,
        "modal-backdrop",
        _detach_success_body(conflict),
        _DETACH_FORM_HIDDEN,
        None,
        None,
    )



_POST_SAVE_VISIBLE = {"display": "flex"}
_POST_SAVE_HIDDEN = {"display": "none"}


def _form_payload(
    extracted_data,
    uploaded_file,
    bl_number,
    doc_type,
    route_type,
    transport_mode,
    zra_regime,
    consignee_name,
    company_name,
    consignee_tin,
    consignor_tin,
    agent_license,
    declarant_number,
    consignment_value,
    origin,
    destination,
    no_containers,
    gross_weight,
    cargo_description,
    gn83_category,
    gn83_unit,
    gn83_fee_usd,
) -> dict:
    return {
        **(extracted_data or {}),
        **{
            "bl_number": bl_number,
            "bl_type": (extracted_data or {}).get("bl_type"),
            "currency": (extracted_data or {}).get("currency"),
            "doc_type": doc_type,
            "route_type": route_type,
            "transport_mode": transport_mode,
            "zra_regime": zra_regime,
            "consignee_name": consignee_name,
            "company_name": company_name,
            "consignee_tin": consignee_tin,
            "consignor_tin": consignor_tin,
            "agent_license": agent_license,
            "agentLicense": agent_license,
            "declarant_number": declarant_number,
            "consignment_value": consignment_value,
            "origin": origin,
            "destination": destination,
            "no_containers": int(no_containers or 0),
            "gross_weight": gross_weight or 0,
            "cargo_description": cargo_description or "General cargo",
            "gn83_category": gn83_category,
            "gn83_unit": gn83_unit,
            "gn83_fee_usd": gn83_fee_usd,
            "file_name": (uploaded_file or {}).get("filename"),
            "file_path": (uploaded_file or {}).get("path"),
        },
    }


def _first_cargo(bl: dict) -> dict:
    cargo_items = bl.get("cargo_items") or []
    return cargo_items[0] if cargo_items else {}


def _confirm_detail(label: str, value) -> html.Div:
    return html.Div(
        [
            html.Span(label),
            html.Strong(str(value if value not in (None, "") else "-")),
        ],
        className="operations-confirm-detail",
    )


def _save_confirm_body(payload: dict, *, is_edit: bool) -> list:
    action = "update this BL and generate a Z-SAD" if is_edit else "save this BL and generate a Z-SAD"
    return [
        html.P(
            f"Please confirm the editable BL values below. If anything is wrong, click Edit Again and correct the form. If everything is correct, ZCAMS will {action}.",
            className="section-lead",
        ),
        html.Div(
            [
                _confirm_detail("BL Number", payload.get("bl_number")),
                _confirm_detail("Document type", payload.get("doc_type")),
                _confirm_detail("Route", payload.get("route_type")),
                _confirm_detail("Transport mode", payload.get("transport_mode")),
                _confirm_detail("ZRA regime", payload.get("zra_regime")),
                _confirm_detail("Company name", payload.get("company_name")),
                _confirm_detail("Consignee", payload.get("consignee_name")),
                _confirm_detail("Consignee TIN", payload.get("consignee_tin")),
                _confirm_detail("Consignor TIN", payload.get("consignor_tin")),
                _confirm_detail("Agent license", payload.get("agent_license")),
                _confirm_detail("Company TIN / TPIN", payload.get("declarant_number")),
                _confirm_detail("Consignment value", payload.get("consignment_value")),
                _confirm_detail("Origin", payload.get("origin")),
                _confirm_detail("Destination", payload.get("destination")),
                _confirm_detail("No. of containers", payload.get("no_containers")),
                _confirm_detail("Gross weight (MT)", payload.get("gross_weight")),
                _confirm_detail("GN 83 category", payload.get("gn83_category")),
                _confirm_detail("GN 83 unit", payload.get("gn83_unit")),
                _confirm_detail("GN 83 fee USD", payload.get("gn83_fee_usd")),
            ],
            className="operations-confirm-grid",
        ),
        html.Div(
            [
                html.Strong("Cargo description"),
                html.P(payload.get("cargo_description") or "General cargo", className="muted"),
            ],
            className="invoice-confirm-panel",
        ),
    ]


@callback(
    Output("bl-result", "children", allow_duplicate=True),
    Output("bl-save-confirm-modal", "className"),
    Output("bl-save-confirm-body", "children"),
    Input("save-bl", "n_clicks"),
    Input("bl-save-confirm-close", "n_clicks"),
    Input("bl-save-edit-again", "n_clicks"),
    State("bl-uploaded-file", "data"),
    State("bl-extracted-data", "data"),
    State("bl-edit-id", "data"),
    State("bl_number", "value"),
    State("doc_type", "value"),
    State("route_type", "value"),
    State("transport_mode", "value"),
    State("zra_regime", "value"),
    State("consignee_name", "value"),
    State("company_name", "value"),
    State("consignee_tin", "value"),
    State("consignor_tin", "value"),
    State("agent_license", "value"),
    State("declarant_number", "value"),
    State("consignment_value", "value"),
    State("origin", "value"),
    State("destination", "value"),
    State("no_containers", "value"),
    State("gross_weight", "value"),
    State("cargo_description", "value"),
    State("gn83_category", "value"),
    State("gn83_unit", "value"),
    State("gn83_fee_usd", "value"),
    prevent_initial_call=True,
)
def toggle_bl_save_confirmation(
    save_clicks,
    _close_clicks,
    _edit_again_clicks,
    uploaded_file,
    extracted_data,
    edit_id,
    bl_number,
    doc_type,
    route_type,
    transport_mode,
    zra_regime,
    consignee_name,
    company_name,
    consignee_tin,
    consignor_tin,
    agent_license,
    declarant_number,
    consignment_value,
    origin,
    destination,
    no_containers,
    gross_weight,
    cargo_description,
    gn83_category,
    gn83_unit,
    gn83_fee_usd,
):
    trigger = ctx.triggered_id
    if trigger in {"bl-save-confirm-close", "bl-save-edit-again"}:
        return no_update, "modal-backdrop is-hidden", no_update
    if trigger != "save-bl" or not save_clicks:
        raise PreventUpdate
    if not str(bl_number or "").strip():
        return html.Div("BL number is required.", className="notice error"), "modal-backdrop is-hidden", no_update
    payload = _form_payload(
        extracted_data,
        uploaded_file,
        bl_number,
        doc_type,
        route_type,
        transport_mode,
        zra_regime,
        consignee_name,
        company_name,
        consignee_tin,
        consignor_tin,
        agent_license,
        declarant_number,
        consignment_value,
        origin,
        destination,
        no_containers,
        gross_weight,
        cargo_description,
        gn83_category,
        gn83_unit,
        gn83_fee_usd,
    )
    return no_update, "modal-backdrop", _save_confirm_body(payload, is_edit=bool(edit_id))


@callback(
    Output("bl-result", "children"),
    Output("bl-table", "children"),
    Output("bl-duplicate-conflict", "data"),
    Output("bl-last-bl-id", "data"),
    Output("bl-post-save-bar", "style"),
    Output("bl-edit-id", "data"),
    Output("save-bl", "children"),
    Output("bl-save-confirm-modal", "className", allow_duplicate=True),
    Input("bl-save-confirm-submit", "n_clicks"),
    State("bl-uploaded-file", "data"),
    State("bl-extracted-data", "data"),
    State("bl-edit-id", "data"),
    State("bl_number", "value"),
    State("doc_type", "value"),
    State("route_type", "value"),
    State("transport_mode", "value"),
    State("zra_regime", "value"),
    State("consignee_name", "value"),
    State("company_name", "value"),
    State("consignee_tin", "value"),
    State("consignor_tin", "value"),
    State("agent_license", "value"),
    State("declarant_number", "value"),
    State("consignment_value", "value"),
    State("origin", "value"),
    State("destination", "value"),
    State("no_containers", "value"),
    State("gross_weight", "value"),
    State("cargo_description", "value"),
    State("gn83_category", "value"),
    State("gn83_unit", "value"),
    State("gn83_fee_usd", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def save_bl(
    _clicks,
    uploaded_file,
    extracted_data,
    edit_id,
    bl_number,
    doc_type,
    route_type,
    transport_mode,
    zra_regime,
    consignee_name,
    company_name,
    consignee_tin,
    consignor_tin,
    agent_license,
    declarant_number,
    consignment_value,
    origin,
    destination,
    no_containers,
    gross_weight,
    cargo_description,
    gn83_category,
    gn83_unit,
    gn83_fee_usd,
    user,
):
    if not _clicks:
        raise PreventUpdate
    company_id = (user or {}).get("company_id") or repository.DEMO_COMPANY_ID
    if not bl_number:
        return (
            html.Div("BL number is required.", className="notice error"),
            _bl_table(repository.list_bls(company_id)),
            None,
            no_update,
            _POST_SAVE_HIDDEN,
            edit_id,
            "Update BL" if edit_id else "Save BL",
            "modal-backdrop is-hidden",
        )
    try:
        payload = _form_payload(
            extracted_data,
            uploaded_file,
            bl_number,
            doc_type,
            route_type,
            transport_mode,
            zra_regime,
            consignee_name,
            company_name,
            consignee_tin,
            consignor_tin,
            agent_license,
            declarant_number,
            consignment_value,
            origin,
            destination,
            no_containers,
            gross_weight,
            cargo_description,
            gn83_category,
            gn83_unit,
            gn83_fee_usd,
        )
        if edit_id:
            bl = repository.update_bl(
                edit_id,
                payload,
                company_id=company_id,
                actor_id=(user or {}).get("id"),
            )
            reviewed = repository.review_bl(bl["id"])
            zsad = reviewed.get("z_sad_number") or "-"
            if is_gn83_exempt(gn83_category):
                follow_up = (
                    "GN 83 exempt cargo — no settlement invoice required. "
                    "Issue cargo release from Reviewed BL when ready."
                )
            else:
                follow_up = "Complete the Full Settlement invoice details next."
            result = html.Div(
                [
                    html.Strong("BL amended and Z-SAD issued."),
                    html.P(f"Z-SAD {zsad} is ready. {follow_up}"),
                ],
                className="notice success",
            )
            return result, _bl_table(repository.list_bls(company_id)), None, bl["id"], _POST_SAVE_VISIBLE, None, "Save BL", "modal-backdrop is-hidden"
        bl = repository.create_bl(payload, auto_review=True, use_ocr_defaults=False, company_id=company_id)
    except BlNumberConflict as exc:
        return _duplicate_notice(exc.conflict), _bl_table(repository.list_bls(company_id)), exc.conflict, no_update, _POST_SAVE_HIDDEN, edit_id, "Update BL" if edit_id else "Save BL", "modal-backdrop is-hidden"
    except ValueError as exc:
        return html.Div(str(exc), className="notice error"), _bl_table(repository.list_bls(company_id)), None, no_update, _POST_SAVE_HIDDEN, edit_id, "Update BL" if edit_id else "Save BL", "modal-backdrop is-hidden"
    reviewed = bl.get("reviewed_bl") or {}
    zsad = reviewed.get("z_sad_number") or "-"
    if is_gn83_exempt(gn83_category):
        follow_up = (
            "GN 83 exempt cargo — no settlement invoice required. "
            "Issue cargo release from Reviewed BL when ready."
        )
    else:
        follow_up = "Complete the Full Settlement invoice details next."
    result = html.Div(
        [
            html.Strong("BL saved and Z-SAD issued."),
            html.P(f"Z-SAD {zsad} is ready. {follow_up}"),
        ],
        className="notice success",
    )
    return result, _bl_table(repository.list_bls(company_id)), None, bl["id"], _POST_SAVE_VISIBLE, None, "Save BL", "modal-backdrop is-hidden"


def save_uploaded_bl(contents: str, filename: str | None) -> Path:
    if "," not in contents:
        raise ValueError("Upload payload was not valid.")
    safe_name = repository.safe_filename(filename or "uploaded-bl.pdf")
    target_dir = UPLOAD_DIR / "bls"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name
    try:
        target.write_bytes(base64.b64decode(contents.split(",", 1)[1]))
    except (binascii.Error, ValueError) as exc:
        raise ValueError("The uploaded BL could not be decoded.") from exc
    return target
