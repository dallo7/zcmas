from dash import html, register_page

from components.layout import header
from components.ui import status_table
from services.gn83 import GN83_FEES


register_page(__name__, path="/gn83", name="GN 83 Schedule")


def layout(**_kwargs):
    sections = []
    for route, modes in GN83_FEES.items():
        for mode, fees in modes.items():
            sections.append(
                html.Div(
                    [
                        html.H2(f"{route} - {mode}"),
                        html.P(
                            "Minimum agency-fee categories used by ZCAMS invoice calculations for this route and transport mode.",
                            className="muted section-lead",
                        ),
                        status_table(
                            ["Category", "Description", "Minimum Fee"],
                            [[key, label, f"${amount:,.2f}"] for key, (label, amount) in fees.items()],
                        ),
                    ],
                    className="card section-card",
                )
            )
    return html.Div(
        [
            header(
                "GN 83 Schedule",
                help_text="Quick reference for GN 83 minimum agency fees. The invoice engine uses these values server-side.",
            ),
            html.Div(sections, className="page-content stack"),
        ]
    )
