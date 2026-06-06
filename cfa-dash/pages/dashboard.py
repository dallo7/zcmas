from dash import Input, Output, callback, dcc, html, register_page

from components.icons import icon
from components.layout import header
from components.ui import metric_card_link
from components.workflow import shortcut_chip
from services import auth, repository


register_page(__name__, path="/dashboard", name="Dashboard")


def _stats_for_user(user: dict | None) -> dict:
    if not user:
        return repository.dashboard_stats()
    if user.get("role") == auth.ROLE_SUPER_ADMIN:
        return repository.dashboard_stats()
    return repository.dashboard_stats(user.get("company_id"))


def _notifications_for_user(user: dict | None) -> list[dict]:
    if not user:
        return repository.list_notifications(limit=10)
    if user.get("role") == auth.ROLE_SUPER_ADMIN:
        return repository.list_notifications(limit=10, company_id=None)
    return repository.list_notifications(limit=10, company_id=user.get("company_id"))


def layout(**_kwargs):
    return html.Div(
        [
            header(
                "Dashboard",
                help_text="Start here. Use quick actions to upload BLs, review cargo, issue Z-SADs, generate invoices, and monitor payments.",
                pathname="/dashboard",
                agentic=True,
            ),
            html.Div(
                [
                    html.Div(id="dashboard-shortcuts", className="shortcut-row"),
                    html.Div(id="dashboard-metrics", className="dashboard-grid"),
                    html.Div(id="dashboard-panels", className="two-column dashboard-panels"),
                ],
                className="page-content stack",
            ),
        ]
    )


@callback(
    Output("dashboard-shortcuts", "children"),
    Output("dashboard-metrics", "children"),
    Output("dashboard-panels", "children"),
    Input("auth-user", "data"),
    prevent_initial_call=False,
)
def refresh_dashboard(user):
    stats = _stats_for_user(user)
    notifications = _notifications_for_user(user)
    shortcuts = [
        shortcut_chip("Upload BL", "/bls", "lucide:file-up", "primary"),
        shortcut_chip("Review & Z-SAD", "/reviewed-bl#active-reviewed-bls", "lucide:file-check-2"),
        shortcut_chip("Request Invoice", "/reviewed-bl#active-reviewed-bls", "lucide:receipt"),
    ]
    if stats.get("outstanding_invoices"):
        shortcuts.append(shortcut_chip("Pay now", "/checkout", "lucide:credit-card", "accent"))
    shortcuts.append(shortcut_chip("Invoice register", "/invoices", "lucide:list"))
    if stats.get("release_pending"):
        shortcuts.append(shortcut_chip("Issue release", "/reviewed-bl#active-reviewed-bls", "lucide:package-check", "accent"))
    metrics = [
        metric_card_link("BLs Uploaded", stats["bls"], "var(--zambia-green)", "/bls"),
        metric_card_link("Reviewed BLs", stats["reviewed"], "var(--zambia-orange)", "/reviewed-bl#active-reviewed-bls"),
        metric_card_link("Active Z-SADs", stats["active_zsads"], "var(--zambia-yellow)", "/reviewed-bl#active-reviewed-bls"),
        metric_card_link("Outstanding Invoices", stats["outstanding_invoices"], "var(--zambia-red)", "/checkout"),
        metric_card_link("Settled Payments", stats["settled_payments"], "var(--zambia-green)", "/invoices"),
    ]
    panels = [
        _updates_panel(stats),
        html.Div(
            [
                html.H2("Recent Notifications"),
                html.P(
                    "Latest system events for the signed-in user or company, with a link to the full notification history.",
                    className="muted section-lead",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Strong(note["event_type"].replace("_", " ").title()),
                                html.P(note["message"], className="muted"),
                            ],
                            className="notification-item",
                        )
                        for note in notifications
                    ]
                    or [html.Div("No notifications yet.", className="muted")],
                    className="dashboard-notification-list",
                ),
                dcc.Link("View all notifications", href="/notifications", className="text-link"),
            ],
            className="card section-card dashboard-notifications-card",
        ),
    ]
    return shortcuts, metrics, panels


def _updates_panel(stats: dict):
    pending_actions = (
        int(stats.get("bls_pending") or 0)
        + int(stats.get("reviewed_invoice_ready") or 0)
        + int(stats.get("checkout_pending") or 0)
        + int(stats.get("release_pending") or 0)
    )
    return html.Div(
        [
            html.H2("Operational Updates"),
            html.P(
                "A quick summary of workflow items that need attention across notifications, BL review, Z-SADs, payments, and release.",
                className="muted section-lead",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(icon("lucide:bell"), className="update-stat-icon"),
                            html.Div(stats.get("notifications_unread") or 0, className="update-stat-value"),
                            html.Div("Unread updates", className="update-stat-label"),
                            html.P("New ZCAMS events waiting in Notifications.", className="muted"),
                            dcc.Link("Open Notifications", href="/notifications", className="text-link"),
                        ],
                        className="update-stat-card",
                    ),
                    html.Div(
                        [
                            html.Div(icon("lucide:timer-reset"), className="update-stat-icon accent"),
                            html.Div(pending_actions, className="update-stat-value accent"),
                            html.Div("Workflow actions", className="update-stat-label"),
                            html.P("BLs, invoices, checkout, or release items that still need attention.", className="muted"),
                            dcc.Link("Continue workflow", href="/reviewed-bl#active-reviewed-bls", className="text-link"),
                        ],
                        className="update-stat-card",
                    ),
                    html.Div(
                        [
                            html.Div(icon("lucide:file-search"), className="update-stat-icon blue"),
                            html.Div(stats.get("bls_pending") or 0, className="update-stat-value blue"),
                            html.Div("BLs pending review", className="update-stat-label"),
                            html.P("Uploaded BLs waiting for review and Z-SAD action.", className="muted"),
                            dcc.Link("Review BLs", href="/bls", className="text-link"),
                        ],
                        className="update-stat-card",
                    ),
                    html.Div(
                        [
                            html.Div(icon("lucide:file-check-2"), className="update-stat-icon yellow"),
                            html.Div(stats.get("active_zsads") or 0, className="update-stat-value yellow"),
                            html.Div("Active Z-SADs", className="update-stat-label"),
                            html.P("Issued declarations currently active in the clearance workflow.", className="muted"),
                            dcc.Link("View Z-SADs", href="/reviewed-bl#active-reviewed-bls", className="text-link"),
                        ],
                        className="update-stat-card",
                    ),
                    html.Div(
                        [
                            html.Div(icon("lucide:credit-card"), className="update-stat-icon purple"),
                            html.Div(stats.get("checkout_pending") or 0, className="update-stat-value purple"),
                            html.Div("Checkout pending", className="update-stat-label"),
                            html.P("Invoices created but not yet cleared through payment.", className="muted"),
                            dcc.Link("Open Check-out", href="/checkout", className="text-link"),
                        ],
                        className="update-stat-card",
                    ),
                    html.Div(
                        [
                            html.Div(icon("lucide:receipt"), className="update-stat-icon red"),
                            html.Div(stats.get("outstanding_invoices") or 0, className="update-stat-value red"),
                            html.Div("Outstanding invoices", className="update-stat-label"),
                            html.P("Invoices awaiting client payment or CapitalPay settlement.", className="muted"),
                            dcc.Link("Open Check-out", href="/checkout", className="text-link"),
                        ],
                        className="update-stat-card",
                    ),
                ],
                className="update-stat-grid",
            ),
        ],
        className="card section-card updates-panel",
    )
