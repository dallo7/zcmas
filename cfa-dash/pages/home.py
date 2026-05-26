from dash import dcc, html, register_page


register_page(__name__, path="/", name="Home", redirect_from=["/home"])


def layout(**_kwargs):
    # route_guard in app.py redirects "/" → "/login" before this renders.
    return html.Div(className="auth-redirect-spacer")
