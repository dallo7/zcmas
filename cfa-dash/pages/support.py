from dash import ALL, Input, Output, State, callback, dcc, html, register_page

from components.layout import header
from components.ui import badge, status_table
from services import repository


register_page(__name__, path="/support", name="Support")


def layout(**_kwargs):
    tickets = repository.list_support_tickets()
    return html.Div(
        [
            header(
                "Support",
                help_text="Agents raise company support tickets here. Company Admin can track and resolve issues.",
            ),
            html.Div(
                [
                    html.Div(id="support-result"),
                    html.Div(
                        [
                            html.H2("Raise Ticket"),
                            html.Div(
                                [
                                    dcc.Input(id="ticket_subject", placeholder="Subject", className="form-control"),
                                    dcc.Dropdown(id="ticket_module", options=[{"label": v, "value": v} for v in ["BL", "Z-SAD", "Invoice", "Check-out", "Contract", "Other"]], value="BL", className="form-control"),
                                    dcc.Dropdown(id="ticket_priority", options=[{"label": v, "value": v} for v in ["Low", "Medium", "High"]], value="Medium", className="form-control"),
                                    dcc.Textarea(id="ticket_description", placeholder="Description", className="form-control textarea"),
                                ],
                                className="form-grid",
                            ),
                            html.Button("Create Ticket", id="create-ticket", className="btn-primary"),
                        ],
                        className="card section-card stack",
                    ),
                    html.Div(
                        [
                            html.H2("Tickets"),
                            status_table(
                                ["Subject", "Module", "Priority", "Status", "Action"],
                                [
                                    [
                                        ticket["subject"],
                                        ticket["linked_module"],
                                        ticket["priority"],
                                        badge(ticket["status"]),
                                        html.Button("Resolve", id={"type": "resolve-ticket", "id": ticket["id"]}, className="btn-secondary", disabled=ticket["status"] == "Resolved"),
                                    ]
                                    for ticket in tickets
                                ],
                            ),
                        ],
                        className="card section-card",
                    ),
                ],
                className="page-content stack",
            ),
        ]
    )


@callback(
    Output("support-result", "children"),
    Input("create-ticket", "n_clicks"),
    Input({"type": "resolve-ticket", "id": ALL}, "n_clicks"),
    State("ticket_subject", "value"),
    State("ticket_description", "value"),
    State("ticket_module", "value"),
    State("ticket_priority", "value"),
    prevent_initial_call=True,
)
def support_actions(_create, _resolve, subject, description, linked_module, priority):
    from dash import ctx, no_update

    trigger = ctx.triggered_id
    if trigger == "create-ticket":
        if not subject:
            return html.Div("Subject is required.", className="notice error")
        ticket = repository.create_support_ticket(subject, description or "", linked_module or "Other", priority or "Medium")
        return html.Div(f"Ticket created: {ticket['subject']}", className="notice success")
    if isinstance(trigger, dict) and trigger.get("type") == "resolve-ticket":
        repository.update_ticket_status(trigger["id"], "Resolved")
        return html.Div("Ticket resolved.", className="notice success")
    return no_update
