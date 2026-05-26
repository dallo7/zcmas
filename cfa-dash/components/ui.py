from dash import html


STATUS_LABELS = {
    "APPROVED": "Approved",
    "PENDING": "Pending",
    "PENDING_APPROVAL": "Pending Approval",
    "UPLOADED": "Uploaded",
    "REVIEWED": "Reviewed",
    "REVIEWED_ZSAD_ISSUED": "Reviewed - Z-SAD Issued",
    "AWAITING_PAYMENT": "Awaiting Payment",
    "SETTLED": "Settled",
    "SETTLED_RELEASE_PENDING": "Settled - Release Pending",
    "CLEARED": "Cleared",
    "RELEASED": "Released",
    "CARGO_RELEASED": "Cargo Released",
    "CANCELLED": "Cancelled",
    "DRAFT": "Draft",
    "SIGNED": "Signed",
    "Open": "Open",
    "In Progress": "In Progress",
    "Resolved": "Resolved",
}


def badge(status: str):
    normalized = status or "PENDING"
    css = {
        "APPROVED": "badge badge-approved",
        "CLEARED": "badge badge-approved",
        "SETTLED": "badge badge-approved",
        "SIGNED": "badge badge-approved",
        "CARGO_RELEASED": "badge badge-approved",
        "PENDING_APPROVAL": "badge badge-awaiting",
        "AWAITING_PAYMENT": "badge badge-awaiting",
        "SETTLED_RELEASE_PENDING": "badge badge-awaiting",
        "CANCELLED": "badge badge-applied",
        "Open": "badge badge-awaiting",
        "In Progress": "badge badge-awaiting",
        "Resolved": "badge badge-approved",
    }.get(normalized, "badge badge-awaiting")
    return html.Span(STATUS_LABELS.get(normalized, normalized.replace("_", " ").title()), className=css)


def detail_item(label: str, value):
    return html.Div(
        [
            html.P(label, className="detail-label"),
            html.P(value if value not in (None, "") else "-", className="detail-value"),
        ]
    )


def metric_chip(label: str, value, bg: str, number_color: str, accent: str):
    return html.Div(
        [
            html.Span(value or 0, className="metric-value", style={"color": number_color}),
            html.Span(label, className="metric-label", style={"color": accent}),
        ],
        className="metric-chip",
        style={"background": bg},
    )


def metric_card(label: str, value, accent: str):
    return html.Div(
        [
            html.Div(value or 0, className="metric-card-value", style={"color": accent}),
            html.Div(label, className="metric-card-label"),
        ],
        className="card metric-card",
    )


def metric_card_link(label: str, value, accent: str, href: str):
    from dash import dcc

    return dcc.Link(
        metric_card(label, value, accent),
        href=href,
        className="metric-card-link",
    )


def status_table(headers: list[str], rows: list[list]):
    return html.Table(
        [
            html.Thead(html.Tr([html.Th(header) for header in headers])),
            html.Tbody(
                [html.Tr([html.Td(cell) for cell in row]) for row in rows]
                if rows
                else [html.Tr(html.Td("No records yet.", colSpan=len(headers), className="muted"))]
            ),
        ],
        className="data-table",
    )
