from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

from components.chat_ui import render_messages
from components.icons import icon
from services import repository

PUBLIC_CHAT_EMPTY = (
    "General knowledge about Zambia: customs, imports, exports, finance and accounts, tax, and law around clearance. "
    "ZCAMS guides you from CFA registration through cargo release."
)

PUBLIC_CHAT_SUGGESTIONS = (
    "How does ZCAMS work?",
    "What is import clearance in Zambia?",
    "Explain GN 83 agency fees",
    "What VAT applies on clearance invoices?",
)


def floating_public_chat():
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            icon("lucide:message-circle", 18),
                                            html.Strong("ZCAMS Chat"),
                                        ],
                                        className="public-chat-panel-title",
                                    ),
                                    html.Button(
                                        icon("lucide:x", 16),
                                        id="public-chat-close",
                                        className="public-chat-close",
                                        type="button",
                                        title="Close chat",
                                    ),
                                ],
                                className="public-chat-panel-header",
                            ),
                            html.P(
                                "Zambia-only: general knowledge on customs, imports, exports, finance, accounts, tax, "
                                "and law. How ZCAMS works.",
                                className="public-chat-panel-lead muted",
                            ),
                            dcc.Store(id="public-chat-history", data=[]),
                            dcc.Store(id="public-chat-pending", data=None),
                            html.Div(
                                render_messages([], empty_text=PUBLIC_CHAT_EMPTY),
                                id="public-chat-messages",
                                className="zcams-chat-window public-chat-window",
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        label,
                                        id={"type": "public-chat-suggest", "label": label},
                                        className="public-chat-suggest",
                                        type="button",
                                    )
                                    for label in PUBLIC_CHAT_SUGGESTIONS
                                ],
                                className="public-chat-suggestions",
                            ),
                            dcc.Textarea(
                                id="public-chat-question",
                                placeholder="Ask about Zambian customs, imports, exports, finance, tax, law, or ZCAMS…",
                                className="form-control textarea chat-composer-input public-chat-input",
                            ),
                            html.Div(
                                [
                                    html.Button("Ask", id="public-chat-ask", className="btn-primary", type="button"),
                                    html.Button("Clear", id="public-chat-clear", className="btn-secondary", type="button"),
                                ],
                                className="chat-actions",
                            ),
                        ],
                        id="public-chat-panel",
                        className="public-chat-panel",
                    ),
                    html.Button(
                        [icon("lucide:message-circle", 20), html.Span("ZCAMS Chat")],
                        id="public-chat-toggle",
                        className="public-chat-fab",
                        type="button",
                        title="Open ZCAMS visitor chat",
                    ),
                ],
                className="public-chat-inner",
            ),
        ],
        id="public-chat-layer",
        className="zcams-public-chat-layer is-hidden",
    )


@callback(
    Output("public-chat-layer", "className"),
    Input("_pages_location", "pathname"),
    Input("auth-user", "data"),
    prevent_initial_call=False,
)
def toggle_public_chat_layer(pathname, user):
    pathname = pathname or "/"
    show_paths = {"/login", "/onboarding", "/tutorials"}
    if user or pathname not in show_paths:
        return "zcams-public-chat-layer is-hidden"
    return "zcams-public-chat-layer"


@callback(
    Output("public-chat-panel", "className"),
    Input("public-chat-toggle", "n_clicks"),
    Input("public-chat-close", "n_clicks"),
    State("public-chat-panel", "className"),
    prevent_initial_call=True,
)
def toggle_public_chat_panel(_open, _close, panel_class):
    panel_class = panel_class or "public-chat-panel"
    is_open = "is-open" in panel_class.split()
    if ctx.triggered_id == "public-chat-close":
        return "public-chat-panel"
    if ctx.triggered_id == "public-chat-toggle":
        return "public-chat-panel is-open" if not is_open else "public-chat-panel"
    return panel_class


def _resolve_public_question(triggered, question):
    if isinstance(triggered, dict) and triggered.get("type") == "public-chat-suggest":
        return (triggered.get("label") or "").strip()
    return (question or "").strip()


@callback(
    Output("public-chat-pending", "data"),
    Output("public-chat-history", "data"),
    Output("public-chat-messages", "children"),
    Output("public-chat-question", "value"),
    Output("public-chat-ask", "disabled"),
    Output("public-chat-clear", "disabled"),
    Input("public-chat-ask", "n_clicks"),
    Input("public-chat-clear", "n_clicks"),
    Input({"type": "public-chat-suggest", "label": ALL}, "n_clicks"),
    State("public-chat-question", "value"),
    State("public-chat-history", "data"),
    prevent_initial_call=True,
)
def queue_public_chat(_ask, _clear, _suggest_clicks, question, history):
    history = list(history or [])

    if ctx.triggered_id == "public-chat-clear":
        return None, [], render_messages([], empty_text=PUBLIC_CHAT_EMPTY), "", False, False

    question = _resolve_public_question(ctx.triggered_id, question)
    if not question:
        return no_update, no_update, no_update, no_update, no_update, no_update

    user_message = {"role": "user", "content": question}
    next_history = [*history, user_message][-24:]
    return (
        question,
        next_history,
        render_messages(next_history, empty_text=PUBLIC_CHAT_EMPTY, thinking=True),
        "",
        True,
        True,
    )


@callback(
    Output("public-chat-history", "data", allow_duplicate=True),
    Output("public-chat-messages", "children", allow_duplicate=True),
    Output("public-chat-pending", "data", allow_duplicate=True),
    Output("public-chat-ask", "disabled", allow_duplicate=True),
    Output("public-chat-clear", "disabled", allow_duplicate=True),
    Input("public-chat-pending", "data"),
    State("public-chat-history", "data"),
    prevent_initial_call=True,
)
def run_public_chat(pending, history):
    if not pending:
        return no_update, no_update, no_update, no_update, no_update

    history = list(history or [])
    prior = history[:-1] if history and history[-1].get("role") == "user" else history
    user_message = history[-1] if history and history[-1].get("role") == "user" else {"role": "user", "content": pending}
    answer_text = repository.public_chat_answer(pending, prior)
    next_history = [*prior, user_message, {"role": "assistant", "content": answer_text}][-24:]
    return (
        next_history,
        render_messages(next_history, empty_text=PUBLIC_CHAT_EMPTY),
        None,
        False,
        False,
    )
