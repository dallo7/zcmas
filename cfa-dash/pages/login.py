from dash import Input, Output, State, callback, dcc, html, no_update, register_page

from components.icons import icon
from services import auth, repository


register_page(__name__, path="/login", name="Login")


def layout(**_kwargs):
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
                                    html.Div(id="login-result"),
                                    html.Div(
                                        [
                                            html.Label("Username or Email"),
                                            dcc.Input(id="login-email", placeholder="Enter your username or email", className="form-control"),
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
