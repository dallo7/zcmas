from __future__ import annotations

from dash import dcc, html

from components.icons import icon


MILESTONES = [
    ("upload", "BL received"),
    ("ocr", "OCR fields extracted"),
    ("validate", "Five-value re-check"),
    ("create_bl", "BL saved"),
    ("zsad", "Z-SAD issued"),
    ("invoice", "Invoice generated"),
    ("share", "Human approved & client notified"),
]


def agentic_button():
    return html.Button(
        [
            icon("lucide:sparkles", 14),
            html.Span("Agentic Mode"),
        ],
        id="agentic-open",
        className="agentic-mode-button",
        title="Run the guided BL to Z-SAD, invoice, and client-share workflow",
        type="button",
    )


def agentic_modal():
    return html.Div(
        [
            dcc.Store(id="agentic-extracted-data"),
            dcc.Store(id="agentic-uploaded-file"),
            dcc.Store(id="agentic-run-state", data={"status": "idle", "completed": []}),
            dcc.Store(id="agentic-invoice-review", data=None),
            dcc.Store(id="agentic-pay-now-url"),
            dcc.Interval(id="agentic-workflow-interval", interval=900, disabled=True, n_intervals=0),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Agentic BL Mode", className="agentic-eyebrow"),
                                    html.H2("Give ZCAMS the BL. The agent prepares the Z-SAD, invoice, and client link."),
                                    html.P(
                                        "Upload a Bill of Lading, add the client email and phone number, then validate the five values that control invoice and Z-SAD generation.",
                                        className="muted",
                                    ),
                                ],
                                className="agentic-modal-title",
                            ),
                            html.Button("×", id="agentic-close", className="modal-close", title="Close", type="button"),
                        ],
                        className="agentic-modal-header",
                    ),
                    html.Div(id="agentic-progress", children=_progress([])),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3("1. Upload BL"),
                                    dcc.Upload(
                                        id="agentic-bl-upload",
                                        children=html.Div([icon("lucide:file-up", 16), html.Span("Upload BL for Agentic Mode")]),
                                        className="agentic-upload-zone",
                                        multiple=False,
                                        accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.doc,.docx",
                                    ),
                                    html.Div(id="agentic-upload-progress"),
                                    html.Div(id="agentic-upload-feedback", className="stack compact"),
                                    html.Div(id="agentic-guidance", className="agentic-guidance"),
                                ],
                                className="agentic-panel",
                            ),
                            html.Div(
                                [
                                    html.H3("2. Client and invoice route"),
                                    html.Label("Client email"),
                                    dcc.Input(id="agentic-client-email", type="email", placeholder="importer@example.com", className="form-control"),
                                    html.Label("Client phone / WhatsApp"),
                                    dcc.Input(id="agentic-client-phone", placeholder="0971234567", className="form-control"),
                                    html.Label("Invoice type"),
                                    dcc.Dropdown(
                                        id="agentic-invoice-type",
                                        value="SERVICE_FEE_ONLY",
                                        options=[
                                            {"label": "Service Fee Only", "value": "SERVICE_FEE_ONLY"},
                                            {"label": "Full Settlement", "value": "FULL_SETTLEMENT"},
                                        ],
                                        clearable=False,
                                        className="zcams-dropdown",
                                    ),
                                    html.Label("Share channels"),
                                    dcc.Checklist(
                                        id="agentic-share-channels",
                                        value=["EMAIL", "WHATSAPP"],
                                        options=[
                                            {"label": "Email", "value": "EMAIL"},
                                            {"label": "WhatsApp", "value": "WHATSAPP"},
                                        ],
                                        className="channel-checklist",
                                    ),
                                ],
                                className="agentic-panel",
                            ),
                        ],
                        className="agentic-two-column",
                    ),
                    html.Div(
                        [
                            html.H3("3. Five-value re-check"),
                            html.P(
                                "The agent pauses here because these values determine whether the BL, Z-SAD, invoice, and client message are correct.",
                                className="muted",
                            ),
                            html.Div(
                                [
                                    _field("BL Number", dcc.Input(id="agentic-bl-number", className="form-control")),
                                    _field("Consignee / Consigner TIN", dcc.Input(id="agentic-tin", className="form-control")),
                                    _field("Gross Weight (MT)", dcc.Input(id="agentic-gross-weight", type="number", className="form-control")),
                                    _field("No. of containers", dcc.Input(id="agentic-no-containers", type="number", min=0, className="form-control")),
                                    _field(
                                        "Cargo / GN 83 category",
                                        dcc.Dropdown(
                                            id="agentic-gn83-category",
                                            options=[
                                                {"label": "20FT container", "value": "20FT_CONTAINER"},
                                                {"label": "40FT container", "value": "40FT_CONTAINER"},
                                                {"label": "Loose cargo / LCL", "value": "LOOSE_LCL"},
                                                {"label": "Motor vehicle", "value": "MOTOR_VEHICLE"},
                                                {"label": "Heavy equipment", "value": "HEAVY_EQUIPMENT"},
                                                {"label": "Dry bulk", "value": "DRY_BULK"},
                                                {"label": "Bulk liquid", "value": "BULK_LIQUID"},
                                            ],
                                            clearable=False,
                                            className="zcams-dropdown",
                                        ),
                                    ),
                                ],
                                className="agentic-validation-grid",
                            ),
                            html.Div(
                                [
                                    dcc.Checklist(
                                        id="agentic-five-confirm",
                                        options=[
                                            {
                                                "label": "I have re-checked the BL number, TIN, gross weight, container/LCL status, and invoice type.",
                                                "value": "CONFIRMED",
                                            }
                                        ],
                                        value=[],
                                        className="channel-checklist",
                                    ),
                                    html.Button(
                                        [
                                            html.Span(className="agentic-run-spinner"),
                                            icon("lucide:wand-sparkles", 14),
                                            html.Span("Run Agentic Workflow"),
                                        ],
                                        id="agentic-start-execution",
                                        className="btn-primary",
                                        type="button",
                                    ),
                                ],
                                className="agentic-validation-alert",
                            ),
                            html.Div(id="agentic-validation-result"),
                        ],
                        className="agentic-panel agentic-five-card",
                    ),
                    html.Div(id="agentic-summary", className="agentic-summary"),
                    html.Div(id="agentic-human-review", className="agentic-summary"),
                ],
                className="invoice-modal-card agentic-modal-card",
            ),
        ],
        id="agentic-mode-modal",
        className="modal-backdrop is-hidden",
    )


def _field(label: str, control):
    return html.Div([html.Label(label), control], className="form-field")


def _progress(completed: list[str] | None, active: str | None = None):
    completed_set = set(completed or [])
    completed_count = len(completed_set)
    pct = round((completed_count / len(MILESTONES)) * 100)
    return html.Div(
        [
            html.Div(
                html.Div(className="agentic-progress-fill", style={"width": f"{pct}%"}),
                className="agentic-progress-track",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("✓" if key in completed_set else "•", className="agentic-milestone-dot"),
                            html.Span(label),
                        ],
                        className=(
                            "agentic-milestone completed"
                            if key in completed_set
                            else "agentic-milestone active"
                            if key == active
                            else "agentic-milestone"
                        ),
                    )
                    for key, label in MILESTONES
                ],
                className="agentic-milestone-row",
            ),
        ],
        className="agentic-progress-wrap",
    )


def render_progress(state: dict | None):
    state = state or {}
    return _progress(state.get("completed") or [], state.get("active"))
