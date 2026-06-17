from __future__ import annotations

import os
import sys
import threading
import uuid
from pathlib import Path

import dash
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
from dash._pages import PAGE_REGISTRY, _import_layouts_from_pages, _path_to_page
from dash.exceptions import MissingCallbackContextException, PreventUpdate
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from components.agentic_mode import agentic_modal, render_progress
from components.layout import sidebar
from components.public_chat import floating_public_chat
import components.public_chat  # noqa: F401 — registers visitor chat callbacks
from components.workflow import workflow_strip
from components.icons import icon
from services import agentic_workflow, auth, repository
from services.invoice_routes import register_invoice_routes
from services.asycuda_routes import register_asycuda_routes
from services.pwa_routes import pwa_enabled, register_pwa_routes
from services.repository import bootstrap


bootstrap()


def _start_chat_warmup() -> None:
    try:
        from services.chat_service import warm_chat_pipeline

        threading.Thread(target=warm_chat_pipeline, daemon=True, name="zcams-chat-warmup").start()
    except Exception:
        pass


_start_chat_warmup()

PWA_META_TAGS = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1, viewport-fit=cover"},
    {"name": "theme-color", "content": "#0a4f20"},
    {"name": "apple-mobile-web-app-capable", "content": "yes"},
    {"name": "apple-mobile-web-app-title", "content": "ZCAMS"},
    {"name": "apple-mobile-web-app-status-bar-style", "content": "black-translucent"},
    {"name": "mobile-web-app-capable", "content": "yes"},
    {"name": "application-name", "content": "ZCAMS"},
]

app = dash.Dash(
    __name__,
    use_pages=False,
    suppress_callback_exceptions=True,
    title="ZCAMS",
    meta_tags=PWA_META_TAGS if pwa_enabled() else None,
)

if pwa_enabled():
    app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        <link rel="manifest" href="/manifest.webmanifest">
        <link rel="apple-touch-icon" href="/assets/zcams-logo.png">
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""
server = app.server
auth.configure_server(server)
register_invoice_routes(server)
register_asycuda_routes(server)
register_pwa_routes(server)

# Register page modules without Dash's built-in page_container router
# (that router uses prevent_initial_call=True and leaves a blank first paint).
_import_layouts_from_pages(app.pages_folder)


def _resolve_loaded_page_module(suffix: str):
    """Return the already-imported page module by its base file name.

    Dash's ``_import_layouts_from_pages`` stores each ``pages/*.py`` module in
    ``sys.modules`` under a name that depends on the runtime's import context
    (e.g. ``pages.reviewed_bl`` when launched from inside ``cfa-dash`` but
    ``pages.pages.reviewed_bl`` when launched from one level up). Re-importing
    the same file under a different qualified name causes every ``@callback``
    decorator to fire twice, leading to duplicate callback registrations that
    Dash silently refuses to dispatch. By grabbing the module instance Dash
    already loaded we avoid the double-import entirely.
    """
    target = f".{suffix}"
    for module_name, module in list(sys.modules.items()):
        if not module:
            continue
        if module_name == suffix or module_name.endswith(target):
            file_path = getattr(module, "__file__", None) or ""
            if file_path.endswith(f"{suffix}.py"):
                return module
    raise ImportError(
        f"Page module {suffix!r} was not loaded by Dash's page auto-discovery. "
        f"Ensure pages/{suffix}.py contains register_page(__name__, ...)."
    )


_reviewed_bl_module = _resolve_loaded_page_module("reviewed_bl")
_bls_module = _resolve_loaded_page_module("bls")
detach_zsad_modal = _reviewed_bl_module.detach_zsad_modal
invoice_request_modal = _reviewed_bl_module.invoice_request_modal
bl_detach_modal = _bls_module.bl_detach_modal

PUBLIC_PATHS = auth.PUBLIC_PATHS
WORKFLOW_HIDDEN = {
    "/super-admin",
    "/operations",
    "/admin",
    "/admin-support",
    "/change-password",
    "/notifications",
    "/support",
    "/chat",
    "/gn83",
    "/contracts",
    "/company-profile",
    "/contract-sign",
}
THEME_DEFAULT_VERSION = "white-default-v2"


def _callback_trigger() -> str | None:
    try:
        if ctx.triggered:
            return ctx.triggered_id
    except MissingCallbackContextException:
        pass
    return "_pages_location"


def _resolve_page_layout(pathname: str):
    path_id = (pathname or "/").strip("/")
    page, variables = _path_to_page(path_id)
    if not page:
        page = next((p for p in PAGE_REGISTRY.values() if p.get("path") == "/login"), None)
    if not page:
        return html.H1("Page not found", style={"padding": "24px"})
    layout = page.get("layout", "")
    if callable(layout):
        layout = layout(**(variables or {}))
    return layout


app.layout = html.Div(
    [
        dcc.Location(id="_pages_location", refresh="callback-nav"),
        dcc.Store(id="auth-user", storage_type="memory"),
        dcc.Store(id="theme-mode", data="light", storage_type="memory"),
        dcc.Store(id="theme-defaulted", data=None, storage_type="memory"),
        dcc.Store(id="invoice-request-reviewed"),
        dcc.Store(id="invoice-open-request"),
        dcc.Store(id="bl-last-bl-id"),
        dcc.Store(id="invoice-settlement-pick"),
        dcc.Store(id="invoice-modal-step", data="details"),
        dcc.Store(id="invoice-settlement-mode", data="FULL_SETTLEMENT"),
        dcc.Store(id="detach-reviewed-id"),
        dcc.Store(id="contract-preview-id"),
        html.Div(
            id="app-root",
            className="zcams-public-shell theme-light",
            children=[
                html.Div(id="sidebar-slot"),
                html.Div(
                    id="main-stack",
                    className="main-area",
                    children=[
                        html.Div(id="super-admin-banner-slot"),
                        html.Div(id="workflow-strip-slot"),
                        html.Div(
                            id="page-slot",
                            className="page-slot",
                            children=_resolve_page_layout("/login"),
                        ),
                        html.Div(id="hash-scroll-sentinel", style={"display": "none"}),
                    ],
                ),
            ],
        ),
        html.Div(
            id="zcams-modal-layer",
            children=[
                invoice_request_modal(),
                detach_zsad_modal(),
                bl_detach_modal(),
                html.Div(id="contract-preview-modal-layer"),
                agentic_modal(),
            ],
        ),
        floating_public_chat(),
    ],
    id="zcams-root",
    className="theme-light",
)

# Pattern-matching buttons live inside page-slot; Dash must know their ids exist.
app.validation_layout = html.Div(
    [
        app.layout,
        html.Div(
            style={"display": "none"},
            children=[
                html.Button(
                    id={"type": "invoice-request", "id": "__validation__", "variant": "choose"},
                    n_clicks=0,
                    type="button",
                ),
                html.Button(
                    id={"type": "invoice-request", "id": "__validation__", "variant": "full"},
                    n_clicks=0,
                    type="button",
                ),
                html.Button(id={"type": "detach-open", "id": 0}, n_clicks=0, type="button"),
                html.Button(id={"type": "review-bl", "id": 0}, n_clicks=0, type="button"),
                html.Button(id={"type": "issue-release", "id": 0}, n_clicks=0, type="button"),
                html.Button(id={"type": "preview-contract", "id": "__validation__"}, n_clicks=0, type="button"),
                html.Button(id={"type": "send-contract", "id": "__validation__"}, n_clicks=0, type="button"),
                html.Button(id="contract-send-email", n_clicks=0, type="button"),
                html.Button(id="contract-send-close", n_clicks=0, type="button"),
                dcc.Store(id="contract-review-email-contract-id"),
                html.Div(id="contract-modal-send-result"),
                html.Button(id={"type": "invoice-download-btn", "id": "__validation__"}, n_clicks=0, type="button"),
                html.Button(id="bl-request-invoice", n_clicks=0, type="button"),
                html.Button(id="bl-open-detach", n_clicks=0, type="button"),
                html.Button(id="bl-detach-close", n_clicks=0, type="button"),
                html.Button(id="bl-detach-close-secondary", n_clicks=0, type="button"),
                html.Button(id="bl-detach-submit", n_clicks=0, type="button"),
                html.Div(id="bl-detach-modal"),
                html.Div(id="bl-detach-body"),
                html.Div(id="bl-detach-form"),
                dcc.Store(id="bl-duplicate-conflict"),
                html.Div(id="bl-result"),
                html.Div(id="bl-table"),
                html.Button(id="agentic-open", n_clicks=0, type="button"),
                html.Button(id="agentic-close", n_clicks=0, type="button"),
                dcc.Upload(id="agentic-bl-upload"),
                html.Button(id="agentic-start-execution", n_clicks=0, type="button"),
                dcc.Checklist(id="agentic-human-approval"),
                html.Button(id="agentic-approve-send", n_clicks=0, type="button"),
                html.Button(id="agentic-pay-now-open", n_clicks=0, type="button"),
                dcc.Store(id="agentic-pay-now-url"),
                html.Button(id="profile-users-prev", n_clicks=0, type="button"),
                html.Button(id="profile-users-next", n_clicks=0, type="button"),
                html.Div(id="profile-users-results"),
                dcc.Store(id="profile-users-page"),
                html.Button(id="profile-docs-prev", n_clicks=0, type="button"),
                html.Button(id="profile-docs-next", n_clicks=0, type="button"),
                html.Div(id="profile-docs-results"),
                dcc.Store(id="profile-docs-page"),
                html.Button(id="tutorial-prev", n_clicks=0, type="button"),
                html.Button(id="tutorial-next", n_clicks=0, type="button"),
                html.Button(id={"type": "tutorial-dot", "index": 0}, n_clicks=0, type="button"),
                dcc.Store(id="tutorial-slide-index"),
                html.Div(id="tutorial-slide-stage"),
                html.Div(id="tutorial-progress"),
                html.Span(id="tutorial-counter"),
                dcc.Input(id="contracts-search"),
                html.Button(id="contracts-prev", n_clicks=0, type="button"),
                html.Button(id="contracts-next", n_clicks=0, type="button"),
                html.Span(id="contracts-page-label"),
                html.Div(id="contract-register"),
                dcc.Store(id="contracts-page"),
                dcc.Store(id="contracts-refresh-token"),
                html.Button(id="public-chat-toggle", n_clicks=0, type="button"),
                html.Button(id="public-chat-close", n_clicks=0, type="button"),
                html.Button(id="public-chat-ask", n_clicks=0, type="button"),
                html.Button(id="public-chat-clear", n_clicks=0, type="button"),
                dcc.Textarea(id="public-chat-question"),
                dcc.Store(id="public-chat-history"),
                html.Div(id="public-chat-messages"),
                html.Div(id="public-chat-panel", className="public-chat-panel"),
                html.Div(id="public-chat-layer", className="zcams-public-chat-layer"),
                html.Button(id={"type": "public-chat-suggest", "label": "__validation__"}, n_clicks=0, type="button"),
            ],
        ),
    ]
)


# Settlement choice cards are in the root modal — handled by server callbacks in reviewed_bl.py.

app.clientside_callback(
    """
    function(hashValue, pathname) {
        const scrollRoot = document.querySelector("#page-slot .page-content");
        if (!hashValue) {
            window.setTimeout(function() {
                if (scrollRoot) {
                    scrollRoot.scrollTo({top: 0, behavior: "smooth"});
                }
            }, 80);
            return "";
        }
        const targetId = String(hashValue).replace(/^#/, "");
        window.setTimeout(function() {
            const target = document.getElementById(targetId);
            if (target) {
                const isAdminTools = pathname === "/admin" && targetId === "tools";
                target.scrollIntoView({
                    behavior: "smooth",
                    block: isAdminTools ? "nearest" : "start"
                });
            }
        }, 120);
        return targetId;
    }
    """,
    Output("hash-scroll-sentinel", "children"),
    Input("_pages_location", "hash"),
    Input("_pages_location", "pathname"),
)


app.clientside_callback(
    """
    function(url) {
        if (!url) { return window.dash_clientside.no_update; }
        try { window.open(url, '_blank', 'noopener'); } catch (e) {}
        return '';
    }
    """,
    Output("agentic-pay-now-url", "data", allow_duplicate=True),
    Input("agentic-pay-now-url", "data"),
    prevent_initial_call=True,
)


@callback(
    Output("auth-user", "data"),
    Input("_pages_location", "pathname"),
    prevent_initial_call=False,
)
def restore_session_user(_pathname: str | None):
    """Hydrate Dash auth state from the server-side session cookie."""
    return auth.current_user()


@callback(
    Output("page-slot", "children"),
    Output("_pages_location", "pathname"),
    Input("_pages_location", "pathname"),
    Input("auth-user", "data"),
    prevent_initial_call=False,
)
def render_page(pathname: str | None, user: dict | None):
    """Render page content on navigation; enforce authentication and RBAC."""
    pathname = pathname or "/"
    triggered = _callback_trigger()

    if pathname == "/logout":
        auth.logout_current_session()
        return _resolve_page_layout("/login"), "/login"

    if pathname == "/":
        return no_update, auth.default_home(user.get("role") if user else None) if user else "/login"

    if not user:
        if pathname not in PUBLIC_PATHS:
            return _resolve_page_layout("/login"), "/login"
        if triggered == "_pages_location":
            return _resolve_page_layout(pathname), no_update
        return no_update, no_update

    if user.get("must_change_password") and pathname != "/change-password":
        return _resolve_page_layout("/change-password"), "/change-password"

    if pathname == "/login":
        return no_update, auth.default_home(user.get("role"))

    if pathname == "/change-password" and not user.get("must_change_password"):
        return no_update, auth.default_home(user.get("role"))

    if pathname not in PUBLIC_PATHS and not auth.path_allowed(user.get("role"), pathname):
        home = auth.default_home(user.get("role"))
        denied = html.Div(
            [
                html.H2("Access restricted"),
                html.P(
                    f"Your role ({auth.role_label(user.get('role'))}) cannot open this module. "
                    f"You were redirected to {home}.",
                    className="muted",
                ),
                dcc.Link("Continue", href=home, className="btn-primary"),
            ],
            className="card section-card page-content",
        )
        return denied, home

    if triggered in ("_pages_location", "auth-user"):
        return _resolve_page_layout(pathname), no_update

    return no_update, no_update


@callback(
    Output("auth-user", "data", allow_duplicate=True),
    Input("_pages_location", "search"),
    prevent_initial_call=True,
)
def logout_from_query(search: str | None):
    if search and "logout=1" in search:
        auth.logout_current_session()
        return None
    raise PreventUpdate


def _theme_value(theme_mode: str | dict | None) -> str:
    if isinstance(theme_mode, dict):
        theme_mode = theme_mode.get("mode")
    return "dark" if theme_mode == "dark" else "light"


@callback(
    Output("sidebar-slot", "children"),
    Output("super-admin-banner-slot", "children"),
    Output("workflow-strip-slot", "children"),
    Output("app-root", "className"),
    Output("zcams-root", "className"),
    Input("_pages_location", "pathname"),
    Input("_pages_location", "hash"),
    Input("auth-user", "data"),
    Input("theme-mode", "data"),
    prevent_initial_call=False,
)
def render_app_chrome(
    pathname: str | None,
    hash_value: str | None = None,
    user: dict | None = None,
    theme_mode: str | dict | None = None,
):
    if isinstance(hash_value, dict):
        theme_mode = user
        user = hash_value
        hash_value = None
    pathname = pathname or "/"
    nav_pathname = f"{pathname}{hash_value or ''}"
    theme = _theme_value(theme_mode)
    triggered = _callback_trigger()

    if pathname in PUBLIC_PATHS or pathname == "/" or not user:
        if triggered == "auth-user" and pathname in PUBLIC_PATHS:
            return no_update, no_update, no_update, no_update, no_update
        return None, None, None, f"zcams-public-shell theme-{theme}", f"theme-{theme}"

    shell_class = "app-shell"
    if user.get("role") == "SUPER_ADMIN":
        shell_class += " super-admin-shell"
    shell_class += f" theme-{theme}"

    show_workflow = pathname not in WORKFLOW_HIDDEN
    return (
        sidebar(nav_pathname, user),
        _super_admin_banner(user),
        workflow_strip(pathname) if show_workflow else None,
        shell_class,
        f"theme-{theme}",
    )


def _super_admin_banner(user: dict | None):
    if not user or user.get("role") != "SUPER_ADMIN":
        return None
    email = user.get("email") or ""
    return html.Div(
        [
            html.Div(
                [
                    icon("lucide:shield-check", 16),
                    html.Strong("Super Admin Console"),
                    html.Span(
                        "Platform-wide oversight for CFA approvals, compliance monitoring, audit events, and support escalation."
                    ),
                ],
                className="super-admin-banner-copy",
            ),
            html.Div(email, className="super-admin-banner-email"),
        ],
        className="super-admin-banner",
    )


@callback(
    Output("theme-mode", "data"),
    Output("theme-defaulted", "data"),
    Input("theme-toggle", "n_clicks"),
    Input("auth-user", "data"),
    Input("_pages_location", "pathname"),
    State("theme-mode", "data"),
    State("theme-defaulted", "data"),
    prevent_initial_call=False,
)
def manage_theme(_clicks, _user, _pathname, theme_mode: str | dict | None, defaulted_version: str | None):
    trigger = _callback_trigger()
    if trigger == "theme-toggle":
        next_theme = "light" if _theme_value(theme_mode) == "dark" else "dark"
        return next_theme, THEME_DEFAULT_VERSION
    if trigger == "auth-user":
        return "light", THEME_DEFAULT_VERSION
    if defaulted_version != THEME_DEFAULT_VERSION:
        return "light", THEME_DEFAULT_VERSION
    return no_update, defaulted_version


@callback(
    Output("agentic-mode-modal", "className"),
    Output("agentic-run-state", "data", allow_duplicate=True),
    Output("agentic-uploaded-file", "data", allow_duplicate=True),
    Output("agentic-extracted-data", "data", allow_duplicate=True),
    Output("agentic-upload-progress", "children", allow_duplicate=True),
    Output("agentic-upload-feedback", "children", allow_duplicate=True),
    Output("agentic-validation-result", "children", allow_duplicate=True),
    Output("agentic-summary", "children", allow_duplicate=True),
    Output("agentic-human-review", "children", allow_duplicate=True),
    Output("agentic-invoice-review", "data", allow_duplicate=True),
    Output("agentic-workflow-interval", "disabled", allow_duplicate=True),
    Input("agentic-open", "n_clicks"),
    Input("agentic-close", "n_clicks"),
    Input("_pages_location", "pathname"),
    prevent_initial_call=True,
)
def toggle_agentic_modal(_open_clicks, _close_clicks, _pathname):
    trigger = ctx.triggered_id
    if trigger == "agentic-open":
        if not _open_clicks:
            raise PreventUpdate
        return (
            "modal-backdrop agentic-backdrop",
            {"status": "idle", "completed": []},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            True,
        )
    if trigger in {"agentic-close", "_pages_location"}:
        return (
            "modal-backdrop is-hidden",
            {"status": "idle", "completed": []},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            True,
        )
    raise PreventUpdate


@callback(
    Output("agentic-progress", "children"),
    Output("agentic-start-execution", "className"),
    Output("agentic-start-execution", "disabled"),
    Input("agentic-run-state", "data"),
)
def update_agentic_progress(state):
    state = state or {}
    is_running = state.get("status") == "running"
    is_locked = is_running or state.get("status") == "awaiting_human_review"
    button_class = "btn-primary agentic-run-button is-running" if is_running else "btn-primary agentic-run-button"
    return render_progress(state), button_class, is_locked


def _agentic_upload_progress(label: str, pct: int, status: str = "active"):
    pct = max(0, min(100, int(pct)))
    return html.Div(
        [
            html.Div(
                [
                    html.Span(label),
                    html.Strong(f"{pct}%"),
                ],
                className="agentic-upload-progress-header",
            ),
            html.Div(
                html.Div(className="agentic-upload-progress-fill", style={"width": f"{pct}%"}),
                className="agentic-upload-progress-track",
            ),
        ],
        className=f"agentic-upload-progress-card {status}",
    )


@callback(
    Output("agentic-uploaded-file", "data"),
    Output("agentic-extracted-data", "data"),
    Output("agentic-upload-progress", "children"),
    Output("agentic-upload-feedback", "children"),
    Output("agentic-guidance", "children"),
    Output("agentic-bl-number", "value"),
    Output("agentic-tin", "value"),
    Output("agentic-gross-weight", "value"),
    Output("agentic-no-containers", "value"),
    Output("agentic-gn83-category", "value"),
    Output("agentic-run-state", "data", allow_duplicate=True),
    Output("agentic-validation-result", "children", allow_duplicate=True),
    Output("agentic-summary", "children", allow_duplicate=True),
    Output("agentic-human-review", "children", allow_duplicate=True),
    Output("agentic-invoice-review", "data", allow_duplicate=True),
    Input("agentic-bl-upload", "contents"),
    State("agentic-bl-upload", "filename"),
    prevent_initial_call=True,
)
def agentic_extract_bl(contents, filename):
    if not contents:
        raise PreventUpdate
    try:
        path = agentic_workflow.save_agentic_upload(contents, filename)
        extracted = agentic_workflow.extract_agentic_bl(str(path))
    except ValueError as exc:
        return (
            None,
            None,
            _agentic_upload_progress("Document processing failed", 100, "error"),
            html.Div(str(exc), className="notice error"),
            None,
            None,
            None,
            None,
            None,
            None,
            {"status": "idle", "completed": []},
            None,
            None,
            None,
            None,
        )
    feedback = html.Div(
        [
            html.Strong("BL is extracted for review."),
            html.P("Review the five values below before Agentic Mode generates anything.", className="muted"),
        ],
        className="notice success",
    )
    state = {"status": "needs_validation", "completed": ["upload", "ocr"], "active": "validate"}
    return (
        {"path": str(path), "filename": filename},
        extracted,
        _agentic_upload_progress("Document uploaded and extracted", 100, "complete"),
        feedback,
        agentic_workflow.agentic_guidance(extracted),
        extracted.get("bl_number"),
        extracted.get("consignee_tin"),
        extracted.get("gross_weight"),
        extracted.get("no_containers"),
        extracted.get("gn83_category") or "LOOSE_LCL",
        state,
        None,
        None,
        None,
        None,
    )


@callback(
    Output("agentic-full-settlement-bank-panel", "className"),
    Input("agentic-invoice-type", "value"),
    prevent_initial_call=False,
)
def toggle_agentic_bank_details(invoice_type):
    return "agentic-bank-panel"


@callback(
    Output("agentic-validation-result", "children", allow_duplicate=True),
    Output("agentic-run-state", "data", allow_duplicate=True),
    Output("agentic-workflow-interval", "disabled", allow_duplicate=True),
    Output("agentic-workflow-interval", "n_intervals"),
    Output("agentic-human-review", "children", allow_duplicate=True),
    Output("agentic-invoice-review", "data", allow_duplicate=True),
    Input("agentic-start-execution", "n_clicks"),
    State("agentic-extracted-data", "data"),
    State("agentic-uploaded-file", "data"),
    State("agentic-bl-number", "value"),
    State("agentic-tin", "value"),
    State("agentic-gross-weight", "value"),
    State("agentic-no-containers", "value"),
    State("agentic-gn83-category", "value"),
    State("agentic-invoice-type", "value"),
    State("agentic-beneficiary-name", "value"),
    State("agentic-beneficiary-bank", "value"),
    State("agentic-beneficiary-account", "value"),
    State("agentic-client-email", "value"),
    State("agentic-client-phone", "value"),
    State("agentic-share-channels", "value"),
    State("agentic-five-confirm", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def start_agentic_workflow(
    clicks,
    extracted,
    uploaded_file,
    bl_number,
    tin,
    gross_weight,
    no_containers,
    gn83_category,
    invoice_type,
    beneficiary_name,
    beneficiary_bank_name,
    beneficiary_account_number,
    email,
    phone,
    channels,
    confirmed,
    user,
):
    if not clicks:
        raise PreventUpdate
    if not extracted or not uploaded_file:
        return html.Div("Upload and OCR a BL before running Agentic Mode.", className="notice error"), no_update, True, 0, no_update, no_update
    data = agentic_workflow.five_value_snapshot(
        extracted,
        bl_number=bl_number,
        consignee_tin=tin,
        gross_weight=gross_weight,
        no_containers=no_containers,
        gn83_category=gn83_category,
        invoice_type=invoice_type,
    )
    try:
        agentic_workflow.validate_five_values(
            data,
            confirmed="CONFIRMED" in (confirmed or []),
            channels=channels,
            email=email,
            phone=phone,
        )
        if invoice_type == "FULL_SETTLEMENT":
            missing_bank = [
                label
                for label, value in (
                    ("Beneficiary / account holder", beneficiary_name),
                    ("Bank name", beneficiary_bank_name),
                    ("Account number", beneficiary_account_number),
                )
                if not str(value or "").strip()
            ]
            if missing_bank:
                raise ValueError("Full Settlement requires bank details: " + ", ".join(missing_bank) + ".")
    except ValueError as exc:
        return html.Div(str(exc), className="notice error"), no_update, True, 0, no_update, no_update
    data["file_name"] = uploaded_file.get("filename")
    if invoice_type == "FULL_SETTLEMENT":
        data.update(
            {
                "beneficiary_name": str(beneficiary_name or "").strip(),
                "beneficiary_bank_name": str(beneficiary_bank_name or "").strip(),
                "beneficiary_account_number": str(beneficiary_account_number or "").strip(),
            }
        )
    run_state = {
        "run_id": uuid.uuid4().hex,
        "status": "running",
        "active": "create_bl",
        "completed": ["upload", "ocr", "validate"],
        "data": data,
        "company_id": (user or {}).get("company_id") or repository.DEMO_COMPANY_ID,
        "email": str(email or "").strip() or None,
        "phone": str(phone or "").strip() or None,
        "channels": channels or ["WHATSAPP"],
    }
    notice = html.Div("Five values confirmed. Agentic Mode is now creating the BL journey.", className="notice success")
    return notice, run_state, False, 0, None, None


@callback(
    Output("agentic-run-state", "data", allow_duplicate=True),
    Output("agentic-summary", "children", allow_duplicate=True),
    Output("agentic-validation-result", "children", allow_duplicate=True),
    Output("agentic-workflow-interval", "disabled", allow_duplicate=True),
    Output("agentic-human-review", "children", allow_duplicate=True),
    Output("agentic-invoice-review", "data", allow_duplicate=True),
    Input("agentic-workflow-interval", "n_intervals"),
    State("agentic-run-state", "data"),
    prevent_initial_call=True,
)
def advance_agentic_workflow(_ticks, state):
    if not state or state.get("status") != "running":
        raise PreventUpdate
    try:
        active = state.get("active")
        completed = list(state.get("completed") or [])
        if active == "create_bl":
            bl = agentic_workflow.create_agentic_bl(state["data"], company_id=state.get("company_id") or repository.DEMO_COMPANY_ID)
            state.update({"bl_id": bl["id"], "active": "zsad"})
            completed.append("create_bl")
        elif active == "zsad":
            reviewed = agentic_workflow.issue_agentic_zsad(state["bl_id"])
            state.update({"reviewed_id": reviewed["id"], "active": "invoice"})
            completed.append("zsad")
        elif active == "invoice":
            invoice = agentic_workflow.generate_agentic_invoice_for_review(
                state["reviewed_id"],
                invoice_type="FULL_SETTLEMENT",
                email=state.get("email"),
                phone=state.get("phone"),
                beneficiary_name=state["data"].get("beneficiary_name"),
                beneficiary_bank_name=state["data"].get("beneficiary_bank_name"),
                beneficiary_account_number=state["data"].get("beneficiary_account_number"),
                idempotency_key=state.get("run_id"),
            )
            reviewed = repository.get_reviewed_bl(state["reviewed_id"])
            summary_data = agentic_workflow.summarize_result(invoice, reviewed, {})
            review_data = {
                "invoice_id": invoice["id"],
                "reviewed_id": state["reviewed_id"],
                "summary": summary_data,
                "email": state.get("email"),
                "phone": state.get("phone"),
                "channels": state.get("channels") or ["WHATSAPP"],
                "beneficiary_name": invoice.get("beneficiary_name"),
                "beneficiary_bank_name": invoice.get("beneficiary_bank_name"),
                "beneficiary_account_number": invoice.get("beneficiary_account_number"),
                "run_id": state.get("run_id"),
            }
            completed.append("invoice")
            state.update({"status": "awaiting_human_review", "active": "share", "summary": summary_data, "invoice_id": invoice["id"]})
            return (
                {**state, "completed": completed},
                _agentic_invoice_review_summary(summary_data),
                html.Div("Invoice generated. Human review is required before client notification is sent.", className="notice success"),
                True,
                _agentic_human_review_panel(summary_data, review_data),
                review_data,
            )
        else:
            raise PreventUpdate
        return {**state, "completed": completed}, no_update, None, False, no_update, no_update
    except Exception as exc:  # noqa: BLE001 - surface operational failure to the modal
        state.update({"status": "error", "active": None})
        return state, no_update, html.Div(f"Agentic Mode stopped: {exc}", className="notice error"), True, no_update, no_update


@callback(
    Output("agentic-run-state", "data", allow_duplicate=True),
    Output("agentic-summary", "children", allow_duplicate=True),
    Output("agentic-validation-result", "children", allow_duplicate=True),
    Output("agentic-human-review", "children", allow_duplicate=True),
    Output("agentic-invoice-review", "data", allow_duplicate=True),
    Input("agentic-approve-send", "n_clicks"),
    State("agentic-human-approval", "value"),
    State("agentic-invoice-review", "data"),
    State("agentic-run-state", "data"),
    prevent_initial_call=True,
)
def approve_agentic_invoice_send(_clicks, approval, review_data, state):
    if not review_data:
        raise PreventUpdate
    if "APPROVED" not in (approval or []):
        return (
            no_update,
            no_update,
            html.Div("Review and approve the generated invoice before client sharing.", className="notice error"),
            no_update,
            no_update,
        )
    try:
        share_results = agentic_workflow.share_agentic_invoice_after_review(
            review_data["invoice_id"],
            email=review_data.get("email"),
            phone=review_data.get("phone"),
            channels=review_data.get("channels") or ["WHATSAPP"],
            idempotency_key=review_data.get("run_id"),
        )
        invoice = repository.get_invoice(review_data["invoice_id"])
        reviewed = repository.get_reviewed_bl(review_data["reviewed_id"])
        summary_data = agentic_workflow.summarize_result(invoice, reviewed, share_results)
        next_state = dict(state or {})
        completed = list(next_state.get("completed") or [])
        if "share" not in completed:
            completed.append("share")
        next_state.update({"status": "done", "active": None, "completed": completed, "summary": summary_data})
        return (
            next_state,
            _agentic_summary(summary_data),
            html.Div("Human review approved. Client notification has now been sent/prepared.", className="notice success"),
            None,
            None,
        )
    except Exception as exc:  # noqa: BLE001 - surface operational failure to the modal
        return (
            no_update,
            no_update,
            html.Div(f"Client sharing failed after approval: {exc}", className="notice error"),
            no_update,
            no_update,
        )


@callback(
    Output("agentic-pay-now-url", "data", allow_duplicate=True),
    Output("agentic-human-review", "children", allow_duplicate=True),
    Output("agentic-validation-result", "children", allow_duplicate=True),
    Input("agentic-pay-now-open", "n_clicks"),
    State("agentic-invoice-review", "data"),
    prevent_initial_call=True,
)
def open_agentic_pay_now(_clicks, review_data):
    if not review_data:
        raise PreventUpdate
    invoice = repository.get_invoice(review_data["invoice_id"])
    reviewed = repository.get_reviewed_bl(review_data["reviewed_id"])
    summary = agentic_workflow.summarize_result(invoice, reviewed, {})
    capitalpay_ref = summary.get("capitalpay_ref") or ""
    if not capitalpay_ref or capitalpay_ref == "-" or capitalpay_ref.startswith("CPAYMOCK"):
        return (
            no_update,
            no_update,
            html.Div("CapitalPay has not returned a real production reference for this invoice. Regenerate with production CapitalPay enabled.", className="notice error"),
        )
    return (
        summary.get("pay_now_url"),
        _agentic_human_review_panel(summary, review_data),
        html.Div("CapitalPay checkout opened. Confirm the payment reference and amount before paying.", className="notice success"),
    )


def _agentic_invoice_review_summary(summary: dict):
    return html.Div(
        [
            html.Div(
                [
                    icon("lucide:shield-check", 18),
                    html.Div(
                        [
                            html.Strong("Invoice generated. Waiting for human review before sending."),
                            html.P("Download and review the invoice PDF, amount, BL, Z-SAD, GN 83 category, and client contacts before approval.", className="muted"),
                        ],
                    ),
                ],
                className="notice success",
            ),
            _agentic_summary_grid(summary),
        ],
        className="agentic-summary-card",
    )


def _agentic_human_review_panel(summary: dict, review_data: dict):
    channels = ", ".join(review_data.get("channels") or [])
    return html.Div(
        [
            html.H3("4. Human invoice review before send-out"),
            html.P(
                "ZCAMS has stopped before client sharing. A human must review the generated invoice and approve the send-out.",
                className="muted",
            ),
            html.Div(
                [
                    html.Div([html.Span("Client email"), html.Strong(review_data.get("email") or "-")]),
                    html.Div([html.Span("Client phone"), html.Strong(review_data.get("phone") or "-")]),
                    html.Div([html.Span("Channels"), html.Strong(channels or "-")]),
                    html.Div([html.Span("Invoice total"), html.Strong(repository.money(summary.get("total") or 0))]),
                    *(
                        [
                            html.Div([html.Span("Beneficiary"), html.Strong(summary.get("beneficiary_name") or "-")]),
                            html.Div([html.Span("Bank"), html.Strong(summary.get("beneficiary_bank_name") or "-")]),
                            html.Div([html.Span("Account"), html.Strong(summary.get("beneficiary_account_number") or "-")]),
                        ]
                        if summary.get("invoice_type") == "FULL_SETTLEMENT"
                        else []
                    ),
                ],
                className="agentic-summary-grid",
            ),
            html.Div(
                [
                    html.A([icon("lucide:download", 14), "Download invoice PDF"], href=summary.get("pdf_url"), target="_blank", className="btn-primary"),
                    html.Button(
                        [icon("lucide:credit-card", 14), "Pay Now"],
                        id="agentic-pay-now-open",
                        n_clicks=0,
                        type="button",
                        className="btn-secondary",
                        title="Open CapitalPay checkout in a new tab after human invoice review",
                    ),
                    html.A([icon("lucide:receipt", 14), "Open invoice register"], href="/invoices", className="btn-secondary"),
                ],
                className="row-actions",
            ),
            html.P(
                "Pay Now opens CapitalPay in a new tab for this generated invoice only. It does not send the invoice to the client; use the approval step below for client notification.",
                className="muted",
            ),
            dcc.Checklist(
                id="agentic-human-approval",
                options=[
                    {
                        "label": "I reviewed the invoice PDF, BL number, Z-SAD, amount, GN 83 category, and client contacts. Approve sending to the client.",
                        "value": "APPROVED",
                    }
                ],
                value=[],
                className="channel-checklist invoice-confirm-check",
            ),
            html.Button(
                [icon("lucide:send", 14), html.Span("Approve and send to client")],
                id="agentic-approve-send",
                className="btn-primary",
                type="button",
            ),
        ],
        className="agentic-panel agentic-five-card",
    )


def _agentic_summary_grid(summary: dict):
    email = summary.get("email") or {}
    email_status = "Email sent" if email.get("sent") else email.get("reason") or "Not sent yet"
    return html.Div(
        [
            html.Div([html.Span("BL"), html.Strong(summary.get("bl_number") or "-")]),
            html.Div([html.Span("Z-SAD"), html.Strong(summary.get("z_sad_number") or "-")]),
            html.Div([html.Span("Invoice"), html.Strong(summary.get("invoice_number") or "-")]),
            html.Div([html.Span("GN 83"), html.Strong(f"{summary.get('gn83_category')} · {summary.get('units')} unit(s)")]),
            html.Div([html.Span("Total"), html.Strong(repository.money(summary.get("total") or 0))]),
            html.Div([html.Span("Email"), html.Strong(email_status)]),
            *(
                [
                    html.Div([html.Span("Settlement bank"), html.Strong(summary.get("beneficiary_bank_name") or "-")]),
                    html.Div([html.Span("Settlement account"), html.Strong(summary.get("beneficiary_account_number") or "-")]),
                ]
                if summary.get("invoice_type") == "FULL_SETTLEMENT"
                else []
            ),
        ],
        className="agentic-summary-grid",
    )


def _agentic_summary(summary: dict):
    actions = [
        html.A([icon("lucide:download", 14), "Download invoice PDF"], href=summary.get("pdf_url"), target="_blank", className="btn-primary"),
    ]
    if summary.get("pay_now_url"):
        actions.append(
            html.A(
                [icon("lucide:credit-card", 14), "Pay Now"],
                href=summary["pay_now_url"],
                target="_blank",
                className="btn-secondary",
            )
        )
    if summary.get("whatsapp_url"):
        actions.append(html.A([icon("lucide:send", 14), "Open WhatsApp"], href=summary["whatsapp_url"], target="_blank", className="btn-secondary"))
    return html.Div(
        [
            html.Div(
                [
                    html.Div(["🎉", "✅", "📧"], className="agentic-celebration-icons"),
                    html.Div(
                        [
                            html.Strong("Agentic workflow complete. Client notification sent."),
                            html.P("The BL is reviewed, Z-SAD and invoice are ready, and the client share step is complete.", className="muted"),
                        ],
                        className="agentic-celebration-copy",
                    ),
                ],
                className="agentic-celebration",
            ),
            html.Div(
                [
                    _agentic_summary_grid(summary),
                ],
            ),
            html.Div(actions, className="row-actions"),
        ],
        className="agentic-summary-card",
    )


if __name__ == "__main__":
    app.run(
        host=os.getenv("DASH_HOST", "127.0.0.1"),
        port=int(os.getenv("DASH_PORT", "8050")),
        debug=os.getenv("DASH_DEBUG", "False").lower() == "true",
    )
