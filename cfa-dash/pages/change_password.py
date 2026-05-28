from dash import Input, Output, State, callback, dcc, html, no_update, register_page

from components.icons import icon
from services import auth, repository


register_page(__name__, path="/change-password", name="Set Password")


def layout(**_kwargs):
    return html.Div(
        [
            html.Div(
                [
                    html.Div(icon("lucide:key-round", 30), className="password-setup-icon"),
                    html.H1("Set Your ZCAMS Password"),
                    html.P(
                        "Use the temporary password from your email once, then create your own password before opening the workspace.",
                        className="muted",
                    ),
                    html.Div(id="change-password-result"),
                    html.Div(
                        [
                            html.Label("Temporary / Current Password"),
                            dcc.Input(
                                id="change-password-current",
                                type="password",
                                className="form-control",
                                placeholder="Password from your ZCAMS email",
                            ),
                        ],
                        className="form-group",
                    ),
                    html.Div(
                        [
                            html.Label("New Password"),
                            dcc.Input(
                                id="change-password-new",
                                type="password",
                                className="form-control",
                                placeholder="At least 8 characters",
                            ),
                        ],
                        className="form-group",
                    ),
                    html.Div(
                        [
                            html.Label("Confirm New Password"),
                            dcc.Input(
                                id="change-password-confirm",
                                type="password",
                                className="form-control",
                                placeholder="Repeat new password",
                            ),
                        ],
                        className="form-group",
                    ),
                    html.Button(
                        [icon("lucide:shield-check", 16), "Set Password & Continue"],
                        id="change-password-submit",
                        className="btn-primary",
                        type="button",
                    ),
                ],
                className="public-card password-setup-card",
            )
        ],
        className="public-page password-setup-page",
    )


@callback(
    Output("change-password-result", "children"),
    Output("auth-user", "data", allow_duplicate=True),
    Output("_pages_location", "pathname", allow_duplicate=True),
    Input("change-password-submit", "n_clicks"),
    State("change-password-current", "value"),
    State("change-password-new", "value"),
    State("change-password-confirm", "value"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def set_first_login_password(_clicks, current_password, new_password, confirm_password, user):
    if not user:
        return html.Div("Your session expired. Please sign in again.", className="notice error"), no_update, "/login"
    if new_password != confirm_password:
        return html.Div("New password and confirmation do not match.", className="notice error"), no_update, no_update
    try:
        updated = repository.change_user_password(user["id"], current_password or "", new_password or "")
    except ValueError as exc:
        return html.Div(str(exc), className="notice error"), no_update, no_update

    session_user = auth.login_user(updated)
    destination = auth.default_home(session_user.get("role"))
    return (
        html.Div("Password set successfully. Opening your workspace...", className="notice success"),
        session_user,
        destination,
    )

