from dash import Input, Output, State, callback, ctx, dcc, html, no_update, register_page

from components.chat_ui import render_messages
from components.layout import header
from services import repository


register_page(__name__, path="/chat", name="ZCAMS Chat")

CHAT_EMPTY = (
    "Start a concise ZCAMS conversation. Answers are grounded in FAQ, "
    "component tutorials, and app documents first."
)


def layout(**_kwargs):
    return html.Div(
        [
            header(
                "ZCAMS Chat",
                help_text="FAQ-grounded assistant for GN 83, Z-SAD, BL review, invoice logic, and Check-out guidance.",
            ),
            html.Div(
                html.Div(
                    [
                        html.H2("Ask ZCAMS"),
                        html.P(
                            "Ask workflow questions about BL review, Z-SAD generation, GN 83 fees, invoices, payments, and cargo release.",
                            className="muted section-lead",
                        ),
                        dcc.Store(id="zcams-chat-history", data=[]),
                        dcc.Store(id="zcams-chat-pending", data=None),
                        html.Div(
                            render_messages([], empty_text=CHAT_EMPTY),
                            id="chat-messages",
                            className="zcams-chat-window",
                        ),
                        dcc.Textarea(
                            id="chat-question",
                            placeholder="Ask about GN 83, Z-SAD, invoices, BL fields...",
                            className="form-control textarea chat-composer-input",
                        ),
                        html.Div(
                            [
                                html.Button("Ask", id="ask-chat", className="btn-primary", type="button"),
                                html.Button("Clear Chat", id="clear-chat", className="btn-secondary", type="button"),
                            ],
                            className="chat-actions",
                        ),
                    ],
                    className="card section-card stack zcams-chat-card",
                ),
                className="page-content",
            ),
        ]
    )


@callback(
    Output("zcams-chat-pending", "data"),
    Output("zcams-chat-history", "data"),
    Output("chat-messages", "children"),
    Output("chat-question", "value"),
    Output("ask-chat", "disabled"),
    Output("clear-chat", "disabled"),
    Input("ask-chat", "n_clicks"),
    Input("clear-chat", "n_clicks"),
    State("chat-question", "value"),
    State("zcams-chat-history", "data"),
    prevent_initial_call=True,
)
def queue_chat(_ask_clicks, _clear_clicks, question, history):
    history = list(history or [])
    if ctx.triggered_id == "clear-chat":
        return None, [], render_messages([], empty_text=CHAT_EMPTY), "", False, False

    if not (question or "").strip():
        return no_update, no_update, no_update, no_update, no_update, no_update

    user_message = {"role": "user", "content": question.strip()}
    next_history = [*history, user_message][-24:]
    return (
        question.strip(),
        next_history,
        render_messages(next_history, empty_text=CHAT_EMPTY, thinking=True),
        "",
        True,
        True,
    )


@callback(
    Output("zcams-chat-history", "data", allow_duplicate=True),
    Output("chat-messages", "children", allow_duplicate=True),
    Output("zcams-chat-pending", "data", allow_duplicate=True),
    Output("ask-chat", "disabled", allow_duplicate=True),
    Output("clear-chat", "disabled", allow_duplicate=True),
    Input("zcams-chat-pending", "data"),
    State("zcams-chat-history", "data"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def run_chat(pending, history, user):
    if not pending:
        return no_update, no_update, no_update, no_update, no_update

    history = list(history or [])
    prior = history[:-1] if history and history[-1].get("role") == "user" else history
    user_message = history[-1] if history and history[-1].get("role") == "user" else {"role": "user", "content": pending}
    answer_text = repository.chat_answer(pending, prior, user=user)
    next_history = [*prior, user_message, {"role": "assistant", "content": answer_text}][-24:]
    return (
        next_history,
        render_messages(next_history, empty_text=CHAT_EMPTY),
        None,
        False,
        False,
    )
