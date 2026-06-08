from __future__ import annotations

from dash import html

from services.help_tutorials import PAGE_TUTORIALS


def render_tutorial_guide(
    title: str,
    summary: str | None = None,
    *,
    tutorials: dict | None = None,
) -> list:
    """Goal / Steps / Outcome guide — same structure as the in-app Help panel."""
    catalog = tutorials or PAGE_TUTORIALS
    tutorial = catalog.get(title)
    if not tutorial:
        return [html.H4(title), html.P(summary or "Tutorial content is not available for this module.")]

    intro = (summary or f"Learn how {title} fits into the ZCAMS workflow.").rstrip(".") + "."
    return [
        html.H4(title),
        html.P(intro, className="help-intro help-summary"),
        html.Div(
            [
                html.Span("Goal", className="help-label help-label-goal"),
                html.P(tutorial["objective"], className="help-objective"),
            ],
            className="help-section help-section-goal",
        ),
        html.Div(
            [
                html.Span("Steps", className="help-label help-label-steps"),
                html.Ol(
                    [
                        html.Li(
                            [
                                html.Span(str(index), className="help-step-number"),
                                html.Span(step, className="help-step-copy"),
                            ]
                        )
                        for index, step in enumerate(tutorial["steps"], start=1)
                    ],
                    className="help-steps",
                ),
            ],
            className="help-section help-section-steps",
        ),
        html.Div(
            [
                html.Span("Outcome", className="help-label help-label-outcome"),
                html.P(tutorial["outcome"], className="help-outcome-text"),
            ],
            className="help-outcome",
        ),
    ]
