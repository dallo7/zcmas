"""Workflow navigation, breadcrumbs, and contextual shortcuts for ZCAMS."""

from __future__ import annotations

from dash import dcc, html

from components.icons import icon
from services import repository


WORKFLOW_STEPS = [
    ("/bls", "lucide:file-up", "1. Upload BL", "bl_uploaded"),
    ("/reviewed-bl#active-reviewed-bls", "lucide:file-check-2", "2. Review & Z-SAD", "zsad_issued"),
    ("/reviewed-bl#active-reviewed-bls", "lucide:receipt", "3. Invoice Generated", "invoice_generated"),
    ("/checkout", "lucide:credit-card", "4. Payment Cleared", "payment_cleared"),
    ("/reviewed-bl#active-reviewed-bls", "lucide:package-check", "5. Cargo Release", "cargo_released"),
]

PATH_ACTIVE_STEP = {
    "/dashboard": 0,
    "/bls": 0,
    "/reviewed-bl": 1,
    "/invoices": 2,
    "/checkout": 3,
}

PAGE_BREADCRUMBS: dict[str, list[tuple[str, str | None]]] = {
    "/dashboard": [("Dashboard", None)],
    "/bls": [("Workflow", "/bls"), ("Bill of Lading", None)],
    "/reviewed-bl": [("Workflow", "/bls"), ("Reviewed BL & Z-SAD", None)],
    "/invoices": [("Workflow", "/reviewed-bl"), ("Invoices", None)],
    "/checkout": [("Workflow", "/invoices"), ("Check-out", None)],
    "/contracts": [("Contracts", None)],
    "/company-profile": [("Company Profile", None)],
    "/notifications": [("Notifications", None)],
    "/support": [("Support", None)],
    "/chat": [("ZCAMS Chat", None)],
    "/gn83": [("GN 83 Schedule", None)],
}


def workflow_strip(pathname: str = "/dashboard") -> html.Div:
    active = PATH_ACTIVE_STEP.get(pathname or "/dashboard", -1)
    counts = repository.workflow_journey_counts()
    completed_steps = sum(1 for *_prefix, key in WORKFLOW_STEPS if counts.get(key, 0) > 0)
    steps = []
    for index, (href, icon_name, label, count_key) in enumerate(WORKFLOW_STEPS):
        cls = "workflow-step"
        if index == active:
            cls += " active"
        if counts.get(count_key, 0) > 0:
            cls += " done"
        steps.append(
            dcc.Link(
                [
                    icon(icon_name, 14),
                    html.Span(label),
                    html.Span(str(counts.get(count_key, 0)), className="workflow-step-count"),
                ],
                href=href,
                className=cls,
                title=label,
            )
        )
        if index < len(WORKFLOW_STEPS) - 1:
            steps.append(html.Span(className="workflow-connector"))
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Customs journey", className="workflow-title"),
                    html.Span(f"{completed_steps}/{len(WORKFLOW_STEPS)} cleared", className="workflow-cleared-count"),
                ],
                className="workflow-label",
            ),
            html.Div(steps, className="workflow-steps"),
            html.Div(
                [
                    html.Div(
                        style={"width": f"{round((completed_steps / len(WORKFLOW_STEPS)) * 100)}%"},
                        className="workflow-progress-fill",
                    )
                ],
                className="workflow-progress-track",
                title=f"{completed_steps} customs journey steps have cleared at least one record.",
            ),
        ],
        className="workflow-strip workflow-strip-animated",
    )


def breadcrumb(pathname: str) -> html.Nav | None:
    crumbs = PAGE_BREADCRUMBS.get(pathname or "/dashboard")
    if not crumbs:
        return None
    items = []
    for label, href in crumbs:
        if not href:
            continue
        if items:
            items.append(html.Span("/", className="breadcrumb-sep"))
        items.append(dcc.Link(label, href=href, className="breadcrumb-link"))
    if not items:
        return None
    return html.Nav(items, className="page-breadcrumb", **{"aria-label": "Breadcrumb"})


def shortcut_chip(label: str, href: str, icon_name: str = "lucide:arrow-right", accent: str = "secondary"):
    return dcc.Link(
        [icon(icon_name, 14), html.Span(label)],
        href=href,
        className=f"shortcut-chip shortcut-chip-{accent}",
    )


def next_step_banner(message: str, *actions):
    return html.Div(
        [
            html.Div([icon("lucide:route", 16), html.Span(message)], className="next-step-copy"),
            html.Div(list(actions), className="next-step-actions") if actions else None,
        ],
        className="next-step-banner",
    )


def nav_badge(count: int, tone: str = "warn") -> html.Span | None:
    if not count:
        return None
    display = str(count) if count < 100 else "99+"
    return html.Span(display, className=f"nav-badge nav-badge-{tone}")


def counts_for_nav(company_id: str | None = None) -> dict:
    return repository.nav_counts(company_id)
