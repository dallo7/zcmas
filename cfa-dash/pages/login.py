from dash import Input, Output, State, callback, dcc, html, no_update, register_page

from components.icons import icon
from services import repository


register_page(__name__, path="/login", name="Login")


def layout(**_kwargs):
    demo_users = repository.list_demo_users()
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
                                    html.H2("Agent Sign In"),
                                    html.P("Use a pre-created demonstration user, or register a CFA company and sign in with the username and password created during registration."),
                                    html.Div(
                                        [
                                            html.Div("Pre-created users", className="login-demo-title"),
                                            *[
                                                html.Div(
                                                    [
                                                        html.Strong(f"{user['first_name']} {user['last_name']}"),
                                                        html.Span(user["role"].replace("_", " ").title()),
                                                        html.Code(f"{user.get('username')} / {user['email']}"),
                                                    ],
                                                    className="login-demo-user",
                                                )
                                                for user in demo_users
                                            ],
                                            html.Small("Password for all demo users: demo123", className="field-hint"),
                                        ],
                                        className="login-demo-users",
                                    ),
                                    html.Div(id="login-result"),
                                    html.Div(
                                        [
                                            html.Label("Username or Email"),
                                            dcc.Input(id="login-email", placeholder="superadmin or admin@zaffa.co.zm", className="form-control"),
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
        return (
            html.Div("Invalid login. Use one of the listed demo users with password demo123.", className="notice error"),
            no_update,
            no_update,
        )
    role = user["role"].replace("_", " ").title()
    return html.Div(f"Signed in as {role}. Opening dashboard...", className="notice success"), "/dashboard", user
