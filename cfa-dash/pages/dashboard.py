from dash import dcc, html, register_page

from components.icons import icon
from components.layout import header
from components.ui import metric_card_link
from components.workflow import shortcut_chip
from services import repository


register_page(__name__, path="/dashboard", name="Dashboard")


def layout(**_kwargs):
    stats = repository.dashboard_stats()
    notifications = repository.list_notifications(limit=10)
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
                    html.Div(shortcuts, className="shortcut-row"),
                    html.Div(
                        [
                            metric_card_link("BLs Uploaded", stats["bls"], "var(--zambia-green)", "/bls"),
                            metric_card_link("Reviewed BLs", stats["reviewed"], "var(--zambia-orange)", "/reviewed-bl#active-reviewed-bls"),
                            metric_card_link("Active Z-SADs", stats["active_zsads"], "var(--zambia-yellow)", "/reviewed-bl#active-reviewed-bls"),
                            metric_card_link(
                                "Outstanding Invoices",
                                stats["outstanding_invoices"],
                                "var(--zambia-red)",
                                "/checkout",
                            ),
                            metric_card_link("Settled Payments", stats["settled_payments"], "var(--zambia-green)", "/invoices"),
                        ],
                        className="dashboard-grid",
                    ),
                    html.Div(
                        [
                            _updates_panel(stats, notifications),
                            html.Div(
                                [
                                    html.H2("Recent Notifications"),
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
                                        or [html.Div("No notifications yet.", className="muted")]
                                        ,
                                        className="dashboard-notification-list",
                                    ),
                                    dcc.Link("View all notifications", href="/notifications", className="text-link"),
                                ],
                                className="card section-card dashboard-notifications-card",
                            ),
                        ],
                        className="two-column dashboard-panels",
                    ),
                    html.Div(
                        [
                            html.Span("Keyboard: "),
                            html.Kbd("Alt+2"),
                            html.Span(" BLs · "),
                            html.Kbd("Alt+3"),
                            html.Span(" Reviewed BL · "),
                            html.Kbd("Alt+4"),
                            html.Span(" Invoices · "),
                            html.Kbd("Alt+5"),
                            html.Span(" Check-out"),
                        ],
                        className="keyboard-hint muted",
                    ),
                ],
                className="page-content stack",
            ),
        ]
    )


def _updates_panel(stats: dict, notifications: list[dict]):
    pending_actions = (
        int(stats.get("bls_pending") or 0)
        + int(stats.get("reviewed_invoice_ready") or 0)
        + int(stats.get("checkout_pending") or 0)
        + int(stats.get("release_pending") or 0)
    )
    latest = notifications[0] if notifications else {}
    latest_label = (latest.get("event_type") or "No updates").replace("_", " ").title()
    latest_message = latest.get("message") or "No recent operational updates yet."
    return html.Div(
        [
            html.H2("Operational Updates"),
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
            html.Div(
                [
                    html.Span("Latest update", className="update-latest-label"),
                    html.Strong(latest_label),
                    html.P(latest_message, className="muted"),
                ],
                className="update-latest-card",
            ),
        ],
        className="card section-card updates-panel",
    )
