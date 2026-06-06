from dash import Input, Output, State, callback, dcc, html, register_page

from components.icons import icon
from components.layout import public_nav
from services import repository


register_page(__name__, path="/onboarding", name="CFA Onboarding")


ZAMBIA_PROVINCES = [
    "Lusaka",
    "Copperbelt",
    "Southern",
    "Eastern",
    "Northern",
    "Luapula",
    "Western",
    "North-Western",
    "Muchinga",
    "Central",
]

BANKS = [
    "Zanaco Bank",
    "First National Bank (FNB)",
    "Standard Chartered Bank Zambia",
    "Stanbic Bank Zambia",
    "Indo Zambia Bank",
    "Atlas Mara Bank Zambia",
    "Absa Bank Zambia",
    "United Bank for Africa (UBA)",
    "Investrust Bank",
    "Access Bank Zambia",
    "Other",
]

REQUIRED_DOCS = [
    ("doc-pacra", "PACRA Certificate of Incorporation", True),
    ("doc-tpin", "ZRA TPIN Certificate", True),
    ("doc-zra", "ZRA Customs Agent Licence", True),
    ("doc-insurance", "Professional Indemnity Insurance Certificate", True),
    ("doc-zaffa", "ZAFFA Membership Certificate", False),
    ("doc-return", "Latest Annual Return (PACRA CR6)", False),
]


def options(values: list[str]) -> list[dict]:
    return [{"label": value, "value": value} for value in values]


def field(label: str, child, required: bool = False, hint: str | None = None):
    return html.Div(
        [
            html.Label([label, html.Span(" *") if required else None]),
            child,
            html.Small(hint, className="field-hint") if hint else None,
        ],
        className="form-group",
    )


def section(title: str, subtitle: str, children):
    return html.Section(
        [
            html.Div([html.H2(title), html.P(subtitle, className="muted")], className="onboarding-section-heading"),
            html.Div(children, className="form-grid"),
        ],
        className="public-card onboarding-section",
    )


def upload_doc(upload_id: str, name: str, required: bool):
    return html.Div(
        [
            html.Div(
                [
                    html.Strong(name),
                    html.Span("Required" if required else "Optional", className="doc-required" if required else "doc-optional"),
                    html.Small(id=f"{upload_id}-filename", className="field-hint"),
                ],
                className="doc-copy",
            ),
            dcc.Upload(
                id=upload_id,
                children=html.Button("Choose File", type="button", className="btn-secondary"),
                multiple=False,
            ),
        ],
        className="doc-upload-row",
    )


def layout(**_kwargs):
    return html.Div(
        [
            dcc.Location(id="onboarding-redirect"),
            public_nav(),
            html.Main(
                [
                    html.Div(
                        [
                            html.Div("ZAFFA approval required", className="public-badge"),
                            html.H1("CFA Company Registration"),
                            html.P(
                                "Submit your contact, company, address, banking, and KYC details. ZAFFA reviews each submission before account activation.",
                                className="public-subtitle",
                            ),
                        ],
                        className="onboarding-hero",
                    ),
                    html.Div(id="onboarding-result"),
                    section(
                        "1. Primary Contact Information",
                        "The Company Administrator who will manage the ZCAMS account.",
                        [
                            field("First Name", dcc.Input(id="ob-first-name", className="form-control", placeholder="Given name"), True),
                            field("Last Name", dcc.Input(id="ob-last-name", className="form-control", placeholder="Surname"), True),
                            field("Email Address", dcc.Input(id="ob-email", type="email", className="form-control", placeholder="admin@company.co.zm"), True),
                            field(
                                "Job Title / Role",
                                dcc.Dropdown(
                                    id="ob-job-title",
                                    options=options(["Managing Director", "Operations Manager", "Compliance Officer", "Senior Clearing Agent", "Company Director", "Other"]),
                                    className="zcams-dropdown",
                                    placeholder="Select role",
                                ),
                                True,
                            ),
                            field("Phone Number", dcc.Input(id="ob-phone", className="form-control", placeholder="+260 97 123 4567"), True),
                            field("WhatsApp Number", dcc.Input(id="ob-whatsapp", className="form-control", placeholder="+260 97 123 4567"), False, "Used for payment link delivery and contract sharing."),
                            field("Login Username", dcc.Input(id="ob-username", className="form-control", placeholder="e.g. copperbelt-admin"), True, "This username is used to sign in after registration."),
                            field("Login Password", dcc.Input(id="ob-password", type="password", className="form-control", placeholder="Create password"), True),
                            field("Confirm Password", dcc.Input(id="ob-password-confirm", type="password", className="form-control", placeholder="Repeat password"), True),
                        ],
                    ),
                    section(
                        "2. Company Details",
                        "Registered company information as it appears on Zambia compliance documents.",
                        [
                            field("Company / Trading Name", dcc.Input(id="ob-company-name", className="form-control"), True),
                            field("PACRA Registration Number", dcc.Input(id="ob-pacra", className="form-control"), True),
                            field("TPIN", dcc.Input(id="ob-tpin", className="form-control"), True),
                            field("ZRA Customs Agent Licence No.", dcc.Input(id="ob-zra-licence", className="form-control"), True),
                            field("ZAFFA Membership Number", dcc.Input(id="ob-zaffa-number", className="form-control")),
                            field("Year Established", dcc.Dropdown(id="ob-year", options=options([str(year) for year in range(2026, 1959, -1)]), className="zcams-dropdown", placeholder="Select year")),
                            field("Number of Employees", dcc.Dropdown(id="ob-employees", options=options(["1 - 5", "6 - 15", "16 - 30", "31 - 50", "51 - 100", "100+"]), className="zcams-dropdown", placeholder="Select")),
                            field("Company Email Address", dcc.Input(id="ob-company-email", type="email", className="form-control")),
                        ],
                    ),
                    section(
                        "3. Address and Bank Details",
                        "Registered office address and CFA bank details used for invoicing.",
                        [
                            field("Physical Address Line 1", dcc.Input(id="ob-address1", className="form-control"), True),
                            field("Address Line 2", dcc.Input(id="ob-address2", className="form-control")),
                            field("City / Town", dcc.Input(id="ob-city", className="form-control"), True),
                            field("Province", dcc.Dropdown(id="ob-province", options=options(ZAMBIA_PROVINCES), className="zcams-dropdown", placeholder="Select province"), True),
                            field("P.O. Box / Postal Address", dcc.Input(id="ob-postal", className="form-control")),
                            field("Office Phone", dcc.Input(id="ob-office-phone", className="form-control")),
                            field("Bank Name", dcc.Dropdown(id="ob-bank-name", options=options(BANKS), className="zcams-dropdown", placeholder="Select bank"), True),
                            field("Account Number", dcc.Input(id="ob-account-number", className="form-control"), True),
                            field("Account Holder Name", dcc.Input(id="ob-account-holder", className="form-control"), True),
                            field("Branch / Sort Code", dcc.Input(id="ob-branch", className="form-control")),
                        ],
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.H2("4. KYC Documents"),
                                    html.P(
                                        "Provide the compliance documents ZAFFA needs to review the CFA registration and approval readiness.",
                                        className="muted section-lead",
                                    ),
                                ],
                                className="onboarding-section-heading",
                            ),
                            html.Div([upload_doc(*doc) for doc in REQUIRED_DOCS], className="doc-list"),
                        ],
                        className="public-card onboarding-section",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.H2("5. Review and Submit"),
                                    html.P(
                                        "Confirm the application is accurate before sending it to Super Admin for onboarding review.",
                                        className="muted section-lead",
                                    ),
                                ],
                                className="onboarding-section-heading",
                            ),
                            html.Div(
                                [
                                    dcc.Checklist(
                                        id="ob-terms",
                                        options=[
                                            {
                                                "label": "I agree to the ZCAMS platform terms, GN 83 compliance rules, Z-SAD single-use policy, and ZAFFA approval process.",
                                                "value": "accepted",
                                            }
                                        ],
                                        className="terms-checklist",
                                    ),
                                    html.Button([icon("lucide:send", 16), "Submit Registration"], id="ob-submit", className="btn-primary"),
                                    dcc.Link("Already approved? Sign in", href="/login", className="public-inline-link"),
                                ],
                                className="submit-row",
                            ),
                        ],
                        className="public-card onboarding-section",
                    ),
                ],
                className="onboarding-page",
            ),
        ],
        className="public-page",
    )


@callback(
    Output("onboarding-result", "children"),
    Input("ob-submit", "n_clicks"),
    State("ob-first-name", "value"),
    State("ob-last-name", "value"),
    State("ob-email", "value"),
    State("ob-job-title", "value"),
    State("ob-phone", "value"),
    State("ob-whatsapp", "value"),
    State("ob-username", "value"),
    State("ob-password", "value"),
    State("ob-password-confirm", "value"),
    State("ob-company-name", "value"),
    State("ob-pacra", "value"),
    State("ob-tpin", "value"),
    State("ob-zra-licence", "value"),
    State("ob-zaffa-number", "value"),
    State("ob-year", "value"),
    State("ob-employees", "value"),
    State("ob-company-email", "value"),
    State("ob-address1", "value"),
    State("ob-address2", "value"),
    State("ob-city", "value"),
    State("ob-province", "value"),
    State("ob-postal", "value"),
    State("ob-bank-name", "value"),
    State("ob-account-number", "value"),
    State("ob-account-holder", "value"),
    State("ob-branch", "value"),
    State("ob-terms", "value"),
    *[State(upload_id, "filename") for upload_id, _name, _required in REQUIRED_DOCS],
    *[State(upload_id, "contents") for upload_id, _name, _required in REQUIRED_DOCS],
    prevent_initial_call=True,
)
def submit_onboarding(
    _clicks,
    first_name,
    last_name,
    email,
    job_title,
    phone,
    whatsapp,
    username,
    password,
    password_confirm,
    company_name,
    pacra,
    tpin,
    zra_licence,
    zaffa_number,
    year,
    employees,
    company_email,
    address1,
    address2,
    city,
    province,
    postal,
    bank_name,
    account_number,
    account_holder,
    branch,
    terms,
    *upload_payload,
):
    doc_count = len(REQUIRED_DOCS)
    filenames = upload_payload[:doc_count]
    contents = upload_payload[doc_count:]
    required_values = [first_name, last_name, email, job_title, phone, username, password, password_confirm, company_name, pacra, tpin, zra_licence, address1, city, province, bank_name, account_number, account_holder]
    if any(not value for value in required_values):
        return html.Div("Please complete all required fields before submitting.", className="notice error")
    if password != password_confirm:
        return html.Div("Password and confirmation do not match.", className="notice error")
    if len(password) < 6:
        return html.Div("Password must be at least 6 characters.", className="notice error")
    if "accepted" not in (terms or []):
        return html.Div("Please accept the ZCAMS platform terms before submitting.", className="notice error")

    missing_docs = [
        name
        for (_upload_id, name, required), filename in zip(REQUIRED_DOCS, filenames, strict=False)
        if required and not filename
    ]
    if missing_docs:
        return html.Div(f"Please upload required document: {missing_docs[0]}.", className="notice error")

    documents = [
        {"name": name, "file_name": filename, "contents": content}
        for (_upload_id, name, _required), filename, content in zip(REQUIRED_DOCS, filenames, contents, strict=False)
        if filename
    ]
    payload = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "job_title": job_title,
        "phone": phone,
        "whatsapp": whatsapp or phone,
        "username": username,
        "password": password,
        "company_name": company_name,
        "pacra_number": pacra,
        "tpin": tpin,
        "zra_licence": zra_licence,
        "zaffa_number": zaffa_number,
        "year_established": year,
        "employee_count": employees,
        "company_email": company_email or email,
        "address_line1": address1,
        "address_line2": address2,
        "city": city,
        "province": province,
        "postal_address": postal,
        "bank_name": bank_name,
        "account_number": account_number,
        "account_holder": account_holder,
        "branch": branch,
    }
    try:
        result = repository.create_onboarding(payload, documents)
    except Exception as exc:
        return html.Div(f"Registration could not be saved: {exc}", className="notice error")

    return html.Div(
        [
            html.Strong("Registration submitted."),
            html.Span(f" Reference: {result['reference']}. ZAFFA review is now pending."),
            html.Br(),
            html.Span(f" Username: {result['username']}. You can now sign in with this username and password."),
            dcc.Link(" Go to login", href="/login", className="public-inline-link"),
        ],
        className="notice success",
    )


@callback(
    [Output(f"{upload_id}-filename", "children") for upload_id, _name, _required in REQUIRED_DOCS],
    [Input(upload_id, "filename") for upload_id, _name, _required in REQUIRED_DOCS],
)
def show_filenames(*filenames):
    return [filename or "No file selected" for filename in filenames]
