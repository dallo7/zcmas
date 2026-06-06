from dash import Input, Output, callback, dcc, html, register_page
from dash.exceptions import PreventUpdate

from components.layout import header
from services import repository


register_page(__name__, path="/notifications", name="Notifications")


def layout(**_kwargs):
    return html.Div(
        [
            header(
                "Notifications",
                help_text="Permanent in-app history of onboarding, BL review, Z-SAD, invoice, payment, release, contract, and support events.",
                pathname="/notifications",
            ),
            html.Div(
                html.Div(
                    [
                        html.Div(id="notification-summary"),
                        html.P(
                            "Use this report to reconstruct ZCAMS events across onboarding, BLs, Z-SADs, invoices, payments, release, contracts, and support.",
                            className="muted section-lead",
                        ),
                        dcc.Input(
                            id="notification-search",
                            placeholder="Search notifications by event, message, company, or entity...",
                            className="form-control report-search",
                        ),
                        html.Div(id="notification-list"),
                    ],
                    className="card section-card stack",
                ),
                className="page-content",
            ),
        ]
    )


def _notification_list(notes: list[dict]):
    if not notes:
        return html.Div("No notifications yet.", className="muted empty-state")
    return html.Div(
        [
            html.Div(
                [
                    html.Strong(note["event_type"].replace("_", " ").title()),
                    html.P(note["message"], className="muted"),
                    html.Small(
                        f"{note.get('created_at') or '-'}"
                        + (f" · {note.get('company_name')}" if note.get("company_name") else ""),
                        className="muted",
                    ),
                ],
                className="notification-item",
            )
            for note in notes
        ]
    )


@callback(
    Output("notification-summary", "children"),
    Output("notification-list", "children"),
    Input("_pages_location", "pathname"),
    Input("auth-user", "data"),
    Input("notification-search", "value"),
    prevent_initial_call=False,
)
def render_notifications(pathname, user, search):
    if (pathname or "") != "/notifications":
        raise PreventUpdate
    company_id = None if (user or {}).get("role") in {"SUPER_ADMIN", "ADMIN"} else (user or {}).get("company_id") or repository.DEMO_COMPANY_ID
    notes = repository.list_notifications(company_id=company_id)
    if search:
        q = search.strip().lower()
        notes = [
            note
            for note in notes
            if q
            in " ".join(
                str(note.get(field) or "")
                for field in ("event_type", "message", "company_name", "created_at", "related_entity_id")
            ).lower()
        ]
    unread = sum(1 for note in notes if not int(note.get("is_read") or 0))
    return (
        html.Div(
            [
                html.H2("Notification History"),
                html.Div(
                    [
                        html.Span(str(len(notes)), className="checkout-stat-value"),
                        html.Span("total notifications", className="checkout-stat-label"),
                        html.Span(str(unread), className="notification-counter-pill"),
                        html.Span("unread", className="checkout-stat-label"),
                    ],
                    className="notification-counter-row",
                ),
            ],
            className="section-heading-block",
        ),
        _notification_list(notes),
    )
