from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update, register_page
from dash.exceptions import PreventUpdate

from components.layout import header
from components.icons import icon
from components.ui import metric_card, metric_card_link, status_table
from services import repository


register_page(__name__, path="/company-profile", name="Company Profile")


DOCUMENT_UPLOAD_ACCEPT = (
    ".pdf,.doc,.docx,.csv,.xls,.xlsx,"
    "application/pdf,application/msword,"
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
    "text/csv,application/vnd.ms-excel,"
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

LOGO_UPLOAD_ACCEPT = ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
DOCUMENT_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx", ".csv", ".xls", ".xlsx"}


def _valid_document_filename(filename: str | None) -> bool:
    if not filename or "." not in filename:
        return False
    return f".{filename.rsplit('.', 1)[-1].lower()}" in DOCUMENT_UPLOAD_EXTENSIONS


def layout(**_kwargs):
    return html.Div(
        [
            header(
                "Company Profile",
                help_text="Shows and edits CFA identity, onboarding values, banking details, users, and compliance score.",
                pathname="/company-profile",
            ),
            html.Div(id="profile-action-result"),
            dcc.Store(id="profile-edit-user-id"),
            dcc.Store(id="profile-pending-user-action"),
            html.Div(
                html.Div(
                    [
                        html.Div(
                            [
                                html.H2("Email notification"),
                                html.Button("x", id="profile-mail-popup-close", className="modal-close", title="Close"),
                            ],
                            className="modal-header",
                        ),
                        html.Div(id="profile-mail-popup-message", className="notice success"),
                        html.Div(
                            html.Button("OK", id="profile-mail-popup-ok", className="btn-primary", type="button"),
                            className="modal-actions",
                        ),
                    ],
                    className="invoice-modal-card",
                ),
                id="profile-mail-popup",
                className="modal-backdrop is-hidden",
            ),
            html.Div(
                html.Div(
                    [
                        html.Div(
                            [
                                html.H2("Confirm action"),
                                html.Button("x", id="profile-confirm-close", className="modal-close", title="Close"),
                            ],
                            className="modal-header",
                        ),
                        html.Div(id="profile-confirm-message", className="notice error"),
                        html.Div(
                            [
                                html.Button("Cancel", id="profile-confirm-cancel", className="btn-secondary", type="button"),
                                html.Button("Yes, continue", id="profile-confirm-submit", className="btn-primary", type="button"),
                            ],
                            className="modal-actions",
                        ),
                    ],
                    className="invoice-modal-card",
                ),
                id="profile-confirm-popup",
                className="modal-backdrop is-hidden",
            ),
            html.Div(id="company-profile-content", className="page-content stack"),
        ]
    )


PROFILE_FIELDS = [
    ("name", "Company Name"),
    ("pacra_number", "PACRA Number"),
    ("tpin", "TPIN"),
    ("zra_licence", "ZRA Licence"),
    ("zaffa_number", "ZAFFA Number"),
    ("year_established", "Year Established"),
    ("employee_count", "Employee Count"),
    ("company_email", "Company Email"),
    ("phone", "Phone"),
    ("whatsapp", "WhatsApp"),
    ("address_line1", "Address Line 1"),
    ("address_line2", "Address Line 2"),
    ("city", "City"),
    ("province", "Province"),
    ("postal_address", "Postal Address"),
    ("bank_name", "Bank Name"),
    ("account_number", "Account Number"),
    ("account_holder", "Account Holder"),
    ("branch", "Branch"),
]


def _field(field_id: str, label: str, value: str | None):
    return html.Div(
        [
            html.Label(label),
            dcc.Input(id=f"profile-{field_id}", value=value or "", className="form-control"),
        ],
        className="form-group",
    )


def _profile_content(company: dict, certs: list[dict], users: list[dict], score: int, unedited_contracts: int):
    company_id = company.get("id") or repository.DEMO_COMPANY_ID
    logo_url = repository.company_logo_url(company_id)
    return [
        html.Div(
            [
                html.Div(
                    [
                        metric_card("Compliance Score", f"{score}%", "var(--zambia-green)"),
                        metric_card("Documents", len(certs), "var(--zambia-orange)"),
                        metric_card("Users", len(users), "var(--zambia-yellow)"),
                        metric_card_link("Unedited Contracts", unedited_contracts, "var(--zambia-orange)", "/contracts"),
                        metric_card("Status", company.get("status", "-"), "var(--zambia-green)"),
                    ],
                    className="dashboard-grid company-profile-metrics",
                ),
                html.Div(
                    [
                        html.H3("Company Logo"),
                        html.Div(
                            html.Img(src=logo_url, className="company-logo-preview") if logo_url
                            else html.Div("No logo uploaded", className="muted company-logo-empty"),
                            id="company-logo-frame",
                            className="company-logo-frame",
                        ),
                        dcc.Upload(
                            id="profile-logo-upload",
                            children=html.Div(["Upload ", html.Strong("company logo")]),
                            className="bl-upload-button",
                            accept=LOGO_UPLOAD_ACCEPT,
                            multiple=False,
                        ),
                        html.Div(id="profile-logo-selected", className="selected-file-note"),
                    ],
                    className="card section-card company-logo-card",
                ),
            ],
            className="company-profile-top-row",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.H2("Editable Company Details"),
                        html.P(
                            "These are the values captured during CFA onboarding. Update them here when company, banking, or contact details change.",
                            className="muted section-lead",
                        ),
                    ],
                    className="section-heading-block",
                ),
                html.Div([_field(field_id, label, company.get(field_id)) for field_id, label in PROFILE_FIELDS], className="form-grid two"),
                html.Button("Save Company Profile", id="save-company-profile", className="btn-primary", type="button"),
            ],
            className="card section-card stack",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.H2("Company ZCAMS Users"),
                        html.P(
                            "These users can log in to ZCAMS and perform company operations such as BL declarations, Z-SAD generation, invoicing, and payment follow-up.",
                            className="muted section-lead",
                        ),
                    ],
                    className="section-heading-block",
                ),
                status_table(
                    ["Name", "Username", "Email", "Role", "Status", "Actions"],
                    [
                        [
                            f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                            user.get("username") or "-",
                            user.get("email") or "-",
                            (user.get("role") or "-").replace("_", " ").title(),
                            user.get("status") or "-",
                            html.Div(
                                [
                                    html.Button(
                                        icon("lucide:pencil", 17),
                                        id={"type": "profile-user-edit", "id": user["id"]},
                                        className="contract-action-icon edit",
                                        type="button",
                                        title="Edit user",
                                    ),
                                    html.Button(
                                        icon("lucide:user-check" if user.get("status") == "SUSPENDED" else "lucide:user-x", 17),
                                        id={"type": "profile-user-toggle", "id": user["id"]},
                                        className="contract-action-icon activate" if user.get("status") == "SUSPENDED" else "contract-action-icon suspend",
                                        type="button",
                                        title="Activate user" if user.get("status") == "SUSPENDED" else "Suspend user",
                                    ),
                                    html.Button(
                                        icon("lucide:trash-2", 17),
                                        id={"type": "profile-user-delete", "id": user["id"]},
                                        className="contract-action-icon delete",
                                        type="button",
                                        title="Delete user",
                                    ),
                                ],
                                className="profile-action-row",
                            ),
                        ]
                        for user in users
                    ],
                ),
            ],
            className="card section-card",
        ),
        html.Div(
            [
                html.H2("Create Agent / Declarant Login"),
                html.P(
                    "Create or edit the agent who will make declarations, generate Z-SADs, and request invoices. New-login credentials are sent to the email entered below.",
                    className="muted section-lead",
                ),
                html.Div(
                    [
                        dcc.Input(id="new-user-first", placeholder="First name", className="form-control"),
                        dcc.Input(id="new-user-last", placeholder="Last name", className="form-control"),
                        dcc.Input(id="new-user-email", placeholder="Email address", type="email", className="form-control"),
                        dcc.Input(id="new-user-phone", placeholder="Phone", className="form-control"),
                        dcc.Input(id="new-user-whatsapp", placeholder="WhatsApp", className="form-control"),
                        dcc.Dropdown(
                            id="new-user-role",
                            options=[
                                {"label": "Declarant / Agent", "value": "DECLARANT"},
                                {"label": "Company Admin", "value": "COMPANY_ADMIN"},
                            ],
                            value="DECLARANT",
                            clearable=False,
                            className="form-control",
                        ),
                    ],
                    className="form-grid two",
                ),
                html.Button("Create Login & Email Credentials", id="create-company-user", className="btn-primary", type="button"),
            ],
            className="card section-card stack",
        ),
        html.Div(
            [
                html.H2("Uploaded Company Documents"),
                html.P(
                    "Upload and manage company compliance documents here.",
                    className="muted section-lead",
                ),
                html.Div(
                    [
                        dcc.Input(id="profile-doc-name", placeholder="Document name", className="form-control"),
                        dcc.Upload(
                            id="profile-doc-upload",
                            children=html.Div(["Drag and drop or ", html.Strong("select company document")]),
                            className="bl-upload-button",
                            accept=DOCUMENT_UPLOAD_ACCEPT,
                            multiple=False,
                        ),
                        html.Div(id="profile-doc-upload-selected", className="selected-file-note"),
                        html.Button("Upload Company Document", id="profile-doc-upload-submit", className="btn-primary", type="button"),
                    ],
                    className="form-grid profile-document-upload-grid",
                ),
                html.Div(_profile_documents_table(certs), className="document-table-wrap"),
            ],
            className="card section-card stack",
        ),
    ]


def _profile_documents_table(certs: list[dict]):
    return status_table(
        ["Name", "File", "Uploaded At", "Actions"],
        [
            [
                dcc.Input(
                    id={"type": "profile-doc-rename-name", "id": cert["id"]},
                    value=cert["name"],
                    className="form-control compact-input",
                ),
                cert.get("file_name") or "-",
                cert["uploaded_at"],
                html.Div(
                    [
                        html.A(
                            icon("lucide:eye", 17),
                            href=repository.certificate_preview_url(cert["id"]),
                            target="_blank",
                            className="contract-action-icon preview",
                            title="Preview document",
                        ),
                        html.Button(
                            icon("lucide:pencil", 17),
                            id={"type": "profile-doc-rename", "id": cert["id"]},
                            className="contract-action-icon edit",
                            type="button",
                            title="Rename document",
                        ),
                        html.Button(
                            icon("lucide:trash-2", 17),
                            id={"type": "profile-doc-delete", "id": cert["id"]},
                            className="contract-action-icon delete",
                            type="button",
                            title="Delete document",
                        ),
                    ],
                    className="profile-action-row",
                ),
            ]
            for cert in certs
        ],
    )


def _mail_popup_message(message: str, *, success: bool = True):
    return html.Div(message, className="notice success" if success else "notice error")


def _reset_user_form_outputs():
    return ["", "", "", "", "", "DECLARANT"]


@callback(
    Output("company-profile-content", "children"),
    Input("_pages_location", "pathname"),
    Input("auth-user", "data"),
    prevent_initial_call=False,
)
def render_company_profile(pathname, user):
    if (pathname or "") != "/company-profile":
        raise PreventUpdate
    company_id = (user or {}).get("company_id") or repository.DEMO_COMPANY_ID
    company = repository.get_company(company_id)
    certs = repository.list_certificates(company_id)
    users = repository.list_company_users(company_id)
    score = repository.compliance_score(company_id)
    unedited_contracts = repository.count_unedited_contracts(company_id)
    return _profile_content(company, certs, users, score, unedited_contracts)


@callback(
    Output("profile-doc-upload-selected", "children"),
    Input("profile-doc-upload", "filename"),
    Input("profile-doc-upload", "contents"),
    prevent_initial_call=True,
)
def show_selected_company_document(filename, contents):
    if not filename:
        return ""
    if not _valid_document_filename(filename):
        return html.Div("Unsupported file selected. Use PDF, Word, CSV, or Excel.", className="notice error compact")
    if not contents:
        return html.Div(f"Waiting to import: {filename}", className="muted")
    return html.Div(f"File imported: {filename}", className="notice success compact")


@callback(
    Output("profile-logo-selected", "children"),
    Output("company-logo-frame", "children"),
    Input("profile-logo-upload", "filename"),
    Input("profile-logo-upload", "contents"),
    prevent_initial_call=True,
)
def show_selected_company_logo(filename, contents):
    if not filename:
        return "", no_update
    if not contents:
        return html.Div(f"Waiting to import logo: {filename}", className="muted"), no_update
    return (
        html.Div(
            f"Logo imported: {filename}. It will replace the current logo when you click Save Company Profile.",
            className="notice success compact",
        ),
        html.Img(src=contents, className="company-logo-preview"),
    )


@callback(
    Output("profile-action-result", "children", allow_duplicate=True),
    Output("company-profile-content", "children", allow_duplicate=True),
    Input("profile-doc-upload-submit", "n_clicks"),
    Input({"type": "profile-doc-rename", "id": ALL}, "n_clicks"),
    Input({"type": "profile-doc-delete", "id": ALL}, "n_clicks"),
    State("profile-doc-name", "value"),
    State("profile-doc-upload", "filename"),
    State("profile-doc-upload", "contents"),
    State({"type": "profile-doc-rename-name", "id": ALL}, "id"),
    State({"type": "profile-doc-rename-name", "id": ALL}, "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def profile_document_actions(
    _doc_clicks,
    _rename_clicks,
    _delete_clicks,
    doc_name,
    doc_filename,
    doc_contents,
    rename_ids,
    rename_values,
    user,
):
    company_id = (user or {}).get("company_id") or repository.DEMO_COMPANY_ID
    trigger = ctx.triggered_id
    try:
        if trigger == "profile-doc-upload-submit":
            cert_name = doc_name or doc_filename
            if not cert_name:
                raise ValueError("Select a document and enter a document name.")
            if not doc_filename or not doc_contents:
                raise ValueError("Select a file before clicking Upload Company Document.")
            if not _valid_document_filename(doc_filename):
                raise ValueError("Please upload a PDF, Word, CSV, or Excel document.")
            repository.add_certificate(cert_name, doc_filename or cert_name, company_id, doc_contents)
            notice = html.Div("Company document uploaded.", className="notice success")
        elif isinstance(trigger, dict) and trigger.get("type") == "profile-doc-rename":
            cert_id = trigger["id"]
            rename_map = {
                item["id"]: value
                for item, value in zip(rename_ids or [], rename_values or [])
            }
            cert = repository.rename_certificate(cert_id, rename_map.get(cert_id), company_id)
            notice = html.Div(f"Document renamed: {cert['name']}", className="notice success")
        elif isinstance(trigger, dict) and trigger.get("type") == "profile-doc-delete":
            repository.delete_certificate(trigger["id"], company_id)
            notice = html.Div("Document deleted.", className="notice success")
        else:
            raise PreventUpdate
    except ValueError as exc:
        notice = html.Div(str(exc), className="notice error")
    company = repository.get_company(company_id)
    certs = repository.list_certificates(company_id)
    users = repository.list_company_users(company_id)
    score = repository.compliance_score(company_id)
    unedited_contracts = repository.count_unedited_contracts(company_id)
    return notice, _profile_content(company, certs, users, score, unedited_contracts)


@callback(
    Output("profile-action-result", "children"),
    Output("company-profile-content", "children", allow_duplicate=True),
    Output("profile-edit-user-id", "data"),
    Output("new-user-first", "value"),
    Output("new-user-last", "value"),
    Output("new-user-email", "value"),
    Output("new-user-phone", "value"),
    Output("new-user-whatsapp", "value"),
    Output("new-user-role", "value"),
    Output("create-company-user", "children"),
    Output("profile-mail-popup-message", "children"),
    Output("profile-mail-popup", "className"),
    Output("profile-pending-user-action", "data"),
    Output("profile-confirm-message", "children"),
    Output("profile-confirm-popup", "className"),
    Input("save-company-profile", "n_clicks"),
    Input("create-company-user", "n_clicks"),
    Input({"type": "profile-user-edit", "id": ALL}, "n_clicks"),
    Input({"type": "profile-user-toggle", "id": ALL}, "n_clicks"),
    Input({"type": "profile-user-delete", "id": ALL}, "n_clicks"),
    Input("profile-mail-popup-close", "n_clicks"),
    Input("profile-mail-popup-ok", "n_clicks"),
    Input("profile-confirm-submit", "n_clicks"),
    Input("profile-confirm-cancel", "n_clicks"),
    Input("profile-confirm-close", "n_clicks"),
    State("auth-user", "data"),
    State("profile-edit-user-id", "data"),
    State("profile-pending-user-action", "data"),
    *[State(f"profile-{field_id}", "value") for field_id, _label in PROFILE_FIELDS],
    State("profile-logo-upload", "filename"),
    State("profile-logo-upload", "contents"),
    State("new-user-first", "value"),
    State("new-user-last", "value"),
    State("new-user-email", "value"),
    State("new-user-phone", "value"),
    State("new-user-whatsapp", "value"),
    State("new-user-role", "value"),
    prevent_initial_call=True,
)
def mutate_company_profile(
    _save_clicks,
    _create_clicks,
    _edit_clicks,
    _toggle_clicks,
    _delete_clicks,
    _popup_close,
    _popup_ok,
    _confirm_submit,
    _confirm_cancel,
    _confirm_close,
    user,
    edit_user_id,
    pending_action,
    *state_values,
):
    company_id = (user or {}).get("company_id") or repository.DEMO_COMPANY_ID
    result = no_update
    edit_id_out = no_update
    new_user_field_out = [no_update, no_update, no_update, no_update, no_update, no_update]
    button_label = no_update
    popup_message = no_update
    popup_class = no_update
    pending_action_out = no_update
    confirm_message = no_update
    confirm_class = no_update
    trigger = ctx.triggered_id
    if not trigger:
        raise PreventUpdate
    if isinstance(trigger, str) and trigger in {"profile-mail-popup-close", "profile-mail-popup-ok"}:
        return (
            no_update,
            no_update,
            no_update,
            *new_user_field_out,
            no_update,
            no_update,
            "modal-backdrop is-hidden",
            no_update,
            no_update,
            no_update,
        )
    if isinstance(trigger, str) and trigger in {"profile-confirm-cancel", "profile-confirm-close"}:
        return (
            no_update,
            no_update,
            no_update,
            *new_user_field_out,
            no_update,
            no_update,
            no_update,
            None,
            no_update,
            "modal-backdrop is-hidden",
        )
    profile_values = state_values[: len(PROFILE_FIELDS)]
    logo_filename = state_values[len(PROFILE_FIELDS)]
    logo_contents = state_values[len(PROFILE_FIELDS) + 1]
    new_user_values = state_values[len(PROFILE_FIELDS) + 2:]
    if trigger == "save-company-profile":
        payload = {field_id: value for (field_id, _label), value in zip(PROFILE_FIELDS, profile_values)}
        try:
            repository.update_company_profile(company_id, payload)
            if logo_filename and logo_contents:
                repository.update_company_logo(company_id, logo_filename, logo_contents)
                result = html.Div("Company profile and logo updated.", className="notice success")
            else:
                result = html.Div("Company profile updated.", className="notice success")
        except ValueError as exc:
            result = html.Div(str(exc), className="notice error")
    elif trigger == "create-company-user":
        first, last, email, phone, whatsapp, role = new_user_values
        try:
            if edit_user_id:
                updated_user = repository.update_company_user(
                    edit_user_id,
                    company_id,
                    str(first or "").strip(),
                    str(last or "").strip(),
                    str(email or "").strip(),
                    str(phone or "").strip(),
                    str(whatsapp or "").strip(),
                    role or "DECLARANT",
                )
                result = html.Div(f"User updated: {updated_user['email']}", className="notice success")
                edit_id_out = None
                new_user_field_out = _reset_user_form_outputs()
                button_label = "Create Login & Email Credentials"
            else:
                new_user = repository.create_company_user(
                    company_id,
                    str(first or "").strip(),
                    str(last or "").strip(),
                    str(email or "").strip(),
                    str(phone or "").strip(),
                    str(whatsapp or "").strip(),
                    role or "DECLARANT",
                )
        except ValueError as exc:
            result = html.Div(str(exc), className="notice error")
        else:
            if not edit_user_id:
                message = f"Login created for {new_user['email']}."
                if new_user.get("email_result", {}).get("sent"):
                    message += " The mail has gone with the login credentials."
                    popup_message = _mail_popup_message(message, success=True)
                    popup_class = "modal-backdrop"
                else:
                    message += f" Email was not confirmed, temporary password: {new_user['temp_password']}"
                    popup_message = _mail_popup_message(message, success=False)
                    popup_class = "modal-backdrop"
                result = html.Div(message, className="notice success")
                new_user_field_out = _reset_user_form_outputs()
    elif isinstance(trigger, dict) and trigger.get("type") == "profile-user-edit":
        selected = repository.get_company_user(trigger["id"], company_id)
        if not selected:
            result = html.Div("Selected user was not found.", className="notice error")
        else:
            result = html.Div(f"Editing {selected['email']}. Update the fields below and save.", className="notice success")
            edit_id_out = selected["id"]
            new_user_field_out = [
                selected.get("first_name") or "",
                selected.get("last_name") or "",
                selected.get("email") or "",
                selected.get("phone") or "",
                selected.get("whatsapp") or "",
                selected.get("role") or "DECLARANT",
            ]
            button_label = "Save User Changes"
    elif isinstance(trigger, dict) and trigger.get("type") == "profile-user-toggle":
        selected = repository.get_company_user(trigger["id"], company_id)
        if not selected:
            result = html.Div("Selected user was not found.", className="notice error")
        else:
            target_status = "ACTIVE" if selected.get("status") == "SUSPENDED" else "SUSPENDED"
            action_label = "activate" if target_status == "ACTIVE" else "suspend"
            pending_action_out = {"type": "toggle", "id": trigger["id"], "target_status": target_status}
            confirm_message = _mail_popup_message(
                f"Are you sure you want to {action_label} {selected.get('email')}?",
                success=False,
            )
            confirm_class = "modal-backdrop"
    elif isinstance(trigger, dict) and trigger.get("type") == "profile-user-delete":
        selected = repository.get_company_user(trigger["id"], company_id)
        if not selected:
            result = html.Div("Selected user was not found.", className="notice error")
        else:
            pending_action_out = {"type": "delete", "id": trigger["id"]}
            confirm_message = _mail_popup_message(
                f"Deleting {selected.get('email')} is permanent. Are you sure you want to delete this ZCAMS user account?",
                success=False,
            )
            confirm_class = "modal-backdrop"
    elif trigger == "profile-confirm-submit":
        if not pending_action or not pending_action.get("id"):
            result = html.Div("No pending action to confirm.", className="notice error")
        elif pending_action.get("type") == "toggle":
            try:
                updated = repository.set_company_user_status(
                    pending_action["id"],
                    company_id,
                    pending_action.get("target_status") or "SUSPENDED",
                )
            except ValueError as exc:
                result = html.Div(str(exc), className="notice error")
            else:
                result = html.Div(f"{updated['email']} is now {updated['status'].lower()}.", className="notice success")
            pending_action_out = None
            confirm_class = "modal-backdrop is-hidden"
        elif pending_action.get("type") == "delete":
            user_id = pending_action["id"]
            try:
                repository.delete_company_user(user_id, company_id)
            except ValueError as exc:
                result = html.Div(str(exc), className="notice error")
            else:
                result = html.Div("User deleted.", className="notice success")
                if edit_user_id == user_id:
                    edit_id_out = None
                    new_user_field_out = _reset_user_form_outputs()
                    button_label = "Create Login & Email Credentials"
            pending_action_out = None
            confirm_class = "modal-backdrop is-hidden"
    company = repository.get_company(company_id)
    certs = repository.list_certificates(company_id)
    users = repository.list_company_users(company_id)
    score = repository.compliance_score(company_id)
    unedited_contracts = repository.count_unedited_contracts(company_id)
    return (
        result,
        _profile_content(company, certs, users, score, unedited_contracts),
        edit_id_out,
        *new_user_field_out,
        button_label,
        popup_message,
        popup_class,
        pending_action_out,
        confirm_message,
        confirm_class,
    )
