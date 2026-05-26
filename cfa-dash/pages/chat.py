from dash import Input, Output, State, callback, ctx, dcc, html, no_update, register_page

from components.layout import header
from services import repository


register_page(__name__, path="/chat", name="ZCAMS Chat")


def _render_assistant_answer(content: str):
    lines = (content or "").splitlines()
    if not any(line.startswith(("Module:", "Goal:", "Steps:", "Outcome:")) for line in lines):
        return html.Div(content or "", className="chat-message-text")

    blocks = []
    step_lines = []
    for line in lines:
        if line.startswith("Module:"):
            blocks.append(html.Div(line.replace("Module:", "", 1).strip(), className="chat-answer-module"))
        elif line.startswith("Goal:"):
            blocks.append(
                html.Div(
                    [html.Span("Goal", className="chat-answer-chip goal"), html.P(line.replace("Goal:", "", 1).strip())],
                    className="chat-answer-part goal",
                )
            )
        elif line.startswith("Steps:"):
            continue
        elif line.startswith("Outcome:"):
            if step_lines:
                blocks.append(
                    html.Div(
                        [html.Span("Steps", className="chat-answer-chip steps"), html.Ol([html.Li(step) for step in step_lines])],
                        className="chat-answer-part steps",
                    )
                )
                step_lines = []
            blocks.append(
                html.Div(
                    [html.Span("Outcome", className="chat-answer-chip outcome"), html.P(line.replace("Outcome:", "", 1).strip())],
                    className="chat-answer-part outcome",
                )
            )
        elif line.strip():
            step_lines.append(line.split(". ", 1)[1] if line[:2].rstrip(".").isdigit() and ". " in line else line.strip())

    if step_lines:
        blocks.append(
            html.Div(
                [html.Span("Steps", className="chat-answer-chip steps"), html.Ol([html.Li(step) for step in step_lines])],
                className="chat-answer-part steps",
            )
        )
    return html.Div(blocks, className="chat-message-text chat-answer-structured")


def _render_messages(history: list[dict] | None):
    if not history:
        return html.Div(
            "Start a concise ZCAMS conversation. Answers are grounded in FAQ, component tutorials, and app documents first.",
            className="chat-empty-state",
        )

    return [
        html.Div(
            [
                html.Div("You" if item.get("role") == "user" else "ZCAMS", className="chat-message-author"),
                html.Div(
                    "Question" if item.get("role") == "user" else "ZCAMS Answer",
                    className="chat-message-type",
                ),
                html.Div(item.get("content") or "", className="chat-message-text")
                if item.get("role") == "user"
                else _render_assistant_answer(item.get("content") or ""),
            ],
            className=f"chat-message {'user' if item.get('role') == 'user' else 'assistant'}",
        )
        for item in history
    ]


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
                        dcc.Store(id="zcams-chat-history", data=[]),
                        html.Div(_render_messages([]), id="chat-messages", className="zcams-chat-window"),
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
    prevent_initial_call=True,
)
def answer(_ask_clicks, _clear_clicks, question, history):
    history = list(history or [])
    if ctx.triggered_id == "clear-chat":
        return [], _render_messages([]), ""

    if not (question or "").strip():
        return no_update, no_update, no_update

    user_message = {"role": "user", "content": question.strip()}
    answer_text = repository.chat_answer(question.strip(), history)
    next_history = [*history, user_message, {"role": "assistant", "content": answer_text}][-24:]
    return next_history, _render_messages(next_history), ""
