from dash import Input, Output, State, callback, ctx, dcc, html, no_update, register_page

from components.chat_ui import render_messages
from components.layout import header
from services import repository


register_page(__name__, path="/chat", name="ZCAMS Chat")


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
                        html.Div(
                            render_messages(
                                [],
                                empty_text=(
                                    "Start a concise ZCAMS conversation. Answers are grounded in FAQ, "
                                    "component tutorials, and app documents first."
                                ),
                            ),
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
    Output("zcams-chat-history", "data"),
    Output("chat-messages", "children"),
    Output("chat-question", "value"),
    Input("ask-chat", "n_clicks"),
    Input("clear-chat", "n_clicks"),
    State("chat-question", "value"),
    State("zcams-chat-history", "data"),
    State("auth-user", "data"),
    prevent_initial_call=True,
)
def answer(_ask_clicks, _clear_clicks, question, history, user):
    history = list(history or [])
    if ctx.triggered_id == "clear-chat":
        return [], render_messages([], empty_text=(
            "Start a concise ZCAMS conversation. Answers are grounded in FAQ, "
            "component tutorials, and app documents first."
        )), ""

    if not (question or "").strip():
        return no_update, no_update, no_update

    user_message = {"role": "user", "content": question.strip()}
    answer_text = repository.chat_answer(question.strip(), history, user=user)
    next_history = [*history, user_message, {"role": "assistant", "content": answer_text}][-24:]
    return next_history, render_messages(next_history, empty_text=(
        "Start a concise ZCAMS conversation. Answers are grounded in FAQ, "
        "component tutorials, and app documents first."
    )), ""
