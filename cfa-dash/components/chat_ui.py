from dash import html


def render_assistant_answer(content: str):
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


def render_thinking_bubble(*, label: str = "Reviewing Zambia customs knowledge"):
    return html.Div(
        [
            html.Div("ZCAMS", className="chat-message-author"),
            html.Div("Thinking", className="chat-message-type"),
            html.Div(
                [
                    html.Span(label, className="chat-thinking-label"),
                    html.Span(
                        [
                            html.Span(className="chat-thinking-dot"),
                            html.Span(className="chat-thinking-dot"),
                            html.Span(className="chat-thinking-dot"),
                        ],
                        className="chat-thinking-dots",
                    ),
                ],
                className="chat-message-text chat-thinking",
            ),
        ],
        className="chat-message assistant is-thinking",
    )


def render_messages(history: list[dict] | None, *, empty_text: str, thinking: bool = False):
    if not history:
        if thinking:
            return [render_thinking_bubble()]
        return html.Div(empty_text, className="chat-empty-state")

    messages = [
        html.Div(
            [
                html.Div("You" if item.get("role") == "user" else "ZCAMS", className="chat-message-author"),
                html.Div(
                    "Question" if item.get("role") == "user" else "ZCAMS Answer",
                    className="chat-message-type",
                ),
                html.Div(item.get("content") or "", className="chat-message-text")
                if item.get("role") == "user"
                else render_assistant_answer(item.get("content") or ""),
            ],
            className=f"chat-message {'user' if item.get('role') == 'user' else 'assistant'}",
        )
        for item in history
    ]
    if thinking:
        messages.append(render_thinking_bubble())
    return messages
