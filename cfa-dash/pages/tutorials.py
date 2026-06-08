from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update, register_page

from components.icons import icon
from components.layout import public_nav
from components.tutorial_guide import render_tutorial_guide


register_page(__name__, path="/tutorials", name="Tutorial")

# Workflow order for the public Basics guide (matches help_tutorials keys).
BASICS_MODULES: list[tuple[str, str]] = [
    (
        "Dashboard",
        "Start here. Use quick actions to upload BLs, review cargo, issue Z-SADs, generate invoices, and monitor payments.",
    ),
    (
        "Agentic Mode",
        "Guided BL-to-invoice workflow with visible milestones — open from the Dashboard header.",
    ),
    (
        "BLs",
        "Classify the customs document, enter or review extracted BL data, then save it for Z-SAD review.",
    ),
    (
        "Reviewed BL",
        "Review uploaded BLs, manage single-use Z-SAD numbers, and move records to invoicing.",
    ),
    (
        "Invoices",
        "Invoices are generated from Reviewed BLs with GN 83 minimum fees, admin fee, and VAT.",
    ),
    (
        "Check-out",
        "Review issued invoices, download PDFs, and open CapitalPay payment links.",
    ),
    (
        "Contracts",
        "Create importer contracts, issue OTP-secured signing links, and track signatures.",
    ),
    (
        "Company Profile",
        "Review CFA identity, onboarding values, banking details, users, and compliance score.",
    ),
    (
        "GN 83 Schedule",
        "Quick reference for GN 83 minimum agency fees used by the invoice engine.",
    ),
    (
        "Notifications",
        "Permanent in-app history of onboarding, BL, Z-SAD, invoice, payment, and support events.",
    ),
    (
        "Support",
        "Raise and track support tickets connected to any ZCAMS module.",
    ),
    (
        "ZCAMS Chat",
        "FAQ-grounded assistant for GN 83, Z-SAD, BL review, invoice logic, and Check-out guidance.",
    ),
]


def _module_card(index: int) -> html.Div:
    title, summary = BASICS_MODULES[index]
    return html.Div(
        render_tutorial_guide(title, summary),
        className="basics-tutorial-card tutorial-help",
    )


def _progress_dots(active: int) -> html.Div:
    return html.Div(
        [
            html.Button(
                className=f"tutorial-dot{' is-active' if idx == active else ''}",
                id={"type": "tutorial-dot", "index": idx},
                title=BASICS_MODULES[idx][0],
                type="button",
            )
            for idx in range(len(BASICS_MODULES))
        ],
        className="tutorial-dots",
    )


def layout(**_kwargs):
    return html.Div(
        [
            dcc.Store(id="tutorial-slide-index", data=0),
            public_nav(active="basics"),
            html.Main(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H1("ZCAMS Basics", className="basics-page-title"),
                                    html.P(
                                        "Module guides with Goal, Steps, and Outcome.",
                                        className="basics-page-lead muted",
                                    ),
                                ],
                                className="basics-page-intro",
                            ),
                            html.Div(id="tutorial-slide-stage", children=_module_card(0)),
                            html.Div(
                                [
                                    html.Button(
                                        [icon("lucide:chevron-left", 16), "Previous"],
                                        id="tutorial-prev",
                                        className="btn-secondary",
                                        type="button",
                                    ),
                                    html.Div(id="tutorial-progress", children=_progress_dots(0)),
                                    html.Span(
                                        id="tutorial-counter",
                                        children=f"1 / {len(BASICS_MODULES)}",
                                        className="tutorial-counter",
                                    ),
                                    html.Button(
                                        ["Next", icon("lucide:chevron-right", 16)],
                                        id="tutorial-next",
                                        className="btn-primary",
                                        type="button",
                                    ),
                                ],
                                className="tutorial-nav-bar basics-nav-bar",
                            ),
                        ],
                        className="basics-shell",
                    ),
                ],
                className="public-tutorial-main basics-tutorial-page",
            ),
        ],
        className="public-page public-tutorial-page",
    )


def _slide_outputs(index: int):
    total = len(BASICS_MODULES)
    index = max(0, min(index, total - 1))
    return _module_card(index), _progress_dots(index), f"{index + 1} / {total}", index


@callback(
    Output("tutorial-slide-stage", "children"),
    Output("tutorial-progress", "children"),
    Output("tutorial-counter", "children"),
    Output("tutorial-slide-index", "data"),
    Input("tutorial-prev", "n_clicks"),
    Input("tutorial-next", "n_clicks"),
    Input({"type": "tutorial-dot", "index": ALL}, "n_clicks"),
    State("tutorial-slide-index", "data"),
    prevent_initial_call=True,
)
def navigate_tutorial(prev_clicks, next_clicks, dot_clicks, current_index):
    current = int(current_index or 0)
    trigger = ctx.triggered_id
    if trigger == "tutorial-prev":
        return _slide_outputs(current - 1)
    if trigger == "tutorial-next":
        return _slide_outputs(current + 1)
    if isinstance(trigger, dict) and trigger.get("type") == "tutorial-dot":
        return _slide_outputs(int(trigger.get("index", 0)))
    return (no_update,) * 4
