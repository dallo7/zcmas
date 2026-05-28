from dash import Input, Output, State, callback, dcc, html, no_update, register_page

from components.icons import icon
from services import auth, repository


register_page(__name__, path="/login", name="Login")


def _demo_user_card(user: dict) -> html.Div:
    role = auth.role_label(user.get("role"))
    return html.Div(
        [
            html.Strong(f"{user['first_name']} {user['last_name']}"),
            html.Span(role),
            html.Code(f"{user.get('username')} / {user['email']}"),
        ],
        className="login-demo-user",
    )


def layout(**_kwargs):
    demo_users = repository.list_demo_users()
    super_admins = [u for u in demo_users if u.get("role") == auth.ROLE_SUPER_ADMIN]
    company_admins = [u for u in demo_users if u.get("role") == auth.ROLE_COMPANY_ADMIN]
    declarants = [u for u in demo_users if repository.normalize_role(u.get("role")) == auth.ROLE_DECLARANT]
    return html.Div(
        [
            html.Nav(
                [
                    dcc.Link(
                        html.Img(
                            src="/assets/zcams-logo.png",
                            alt="ZCAMS — ZAFFA CFA Portal",
                            className="public-logo-img",
                        ),
                        href="/login",
                        className="public-logo",
                    ),
                    html.Div(
                        [
                            dcc.Link("Register CFA", href="/onboarding", className="btn-public-outline"),
                            dcc.Link("Sign In", href="/login", className="btn-public-solid"),
                        ],
                        className="public-nav-actions",
                    ),
                ],
                className="public-nav",
            ),
            html.Main(
                [
                    html.Section(
                        [
                            html.H1(["Zambia's Digital ", html.Span("Customs Clearance"), " Command Centre"]),
                            html.P(
                                "ZCAMS manages CFA onboarding, BL review, Z-SAD generation, GN 83 minimum fee enforcement, CapitalPay invoicing, and cargo release activation."
                            ),
                            html.Div(
                                [
                                    dcc.Link([icon("lucide:user-plus", 18), "Register Your CFA"], href="/onboarding", className="btn-public-solid large"),
                                ],
                                className="public-hero-actions",
                            ),
                            html.Div(
                                [
                                    html.Div([html.Strong("ZRA"), html.Span("Compliant")]),
                                    html.Div([html.Strong("GN 83"), html.Span("Gazette Notice enforced")]),
                                    html.Div([html.Strong("Z-SAD"), html.Span("One-time verification")]),
                                ],
                                className="public-stat-row",
                            ),
                        ],
                        className="public-hero",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.H2("Sign In"),
                                    html.P(
                                        "Three ZCAMS roles: Super Admin (platform), Company Admin (tenant), "
                                        "and Declarant / Agent (operational clearance only)."
                                    ),
                                    html.Div(
                                        [
                                            html.Div("Demo accounts (password: demo123)", className="login-demo-title"),
                                            html.Div("Super Admin", className="login-demo-group-label") if super_admins else None,
                                            *[_demo_user_card(user) for user in super_admins],
                                            html.Div("Company Admin", className="login-demo-group-label") if company_admins else None,
                                            *[_demo_user_card(user) for user in company_admins],
                                            html.Div("Declarant / Agent", className="login-demo-group-label") if declarants else None,
                                            *[_demo_user_card(user) for user in declarants],
                                        ],
                                        className="login-demo-users",
                                    ),
                                    html.Div(id="login-result"),
                                    html.Div(
                                        [
                                            html.Label("Username or Email"),
                                            dcc.Input(id="login-email", placeholder="superadmin, companyadmin, or agent", className="form-control"),
                                        ],
                                        className="form-group",
                                    ),
                                    html.Div(
                                        [
                                            html.Label("Password"),
                                            dcc.Input(id="login-password", type="password", placeholder="Password", className="form-control"),
                                        ],
                                        className="form-group",
                                    ),
                                    html.Button("Sign In to ZCAMS", id="login-submit", className="btn-primary"),
                                    html.P(
                                        ["Do not have an account? ", dcc.Link("Register your CFA", href="/onboarding", className="public-inline-link")],
                                        className="public-note",
                                    ),
                                ],
                                className="public-card login-card",
                            )
                        ],
                        className="public-panel",
                    ),
                ],
                className="public-page-grid",
            ),
        ],
        className="public-page",
    )


@callback(
    Output("login-result", "children"),
    Output("_pages_location", "pathname", allow_duplicate=True),
    Output("auth-user", "data"),
    Input("login-submit", "n_clicks"),
    State("login-email", "value"),
    State("login-password", "value"),
    prevent_initial_call=True,
)
def login(_clicks, email, password):
    user = repository.authenticate_user(email, password)
    if not user:
        auth.record_login_event(email=(email or "").strip(), user_id=None, success=False, failure_reason="Invalid credentials")
        return (
            html.Div("Invalid login. Check username/email and password.", className="notice error"),
            no_update,
            no_update,
        )
    session_user = auth.login_user(user)
    role = auth.role_label(session_user.get("role"))
    destination = "/change-password" if session_user.get("must_change_password") else auth.default_home(session_user.get("role"))
    return (
        html.Div(f"Signed in as {role}. Opening your workspace...", className="notice success"),
        destination,
        session_user,
    )
