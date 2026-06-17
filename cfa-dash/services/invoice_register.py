"""Invoice register filtering and pagination helpers."""

from __future__ import annotations

from services import repository

INVOICE_PAGE_SIZE = 25


def filter_invoice_rows(invoices: list[dict], filter_mode: str = "all", search_value: str | None = None) -> list[dict]:
    filtered = invoices
    if filter_mode == "outstanding":
        filtered = [inv for inv in invoices if inv["status"] != "SETTLED"]
    elif filter_mode == "settled":
        filtered = [inv for inv in invoices if inv["status"] == "SETTLED"]
    query = str(search_value or "").strip().lower()
    if query:
        filtered = [
            inv
            for inv in filtered
            if query in str(inv.get("invoice_number") or "").lower()
            or query in repository.invoice_capitalpay_number(inv).lower()
            or query in str(inv.get("bl_number") or "").lower()
            or query in str(inv.get("z_sad_number") or "").lower()
        ]
    return filtered


def paginate_invoice_rows(rows: list[dict], page: int | None, *, page_size: int = INVOICE_PAGE_SIZE) -> tuple[list[dict], int, int]:
    total_pages = max(1, ((len(rows) - 1) // page_size) + 1) if rows else 1
    current = max(1, min(int(page or 1), total_pages))
    start = (current - 1) * page_size
    return rows[start : start + page_size], current, total_pages


def invoice_register_counts(invoices: list[dict]) -> tuple[int, int, int]:
    total = len(invoices)
    outstanding = sum(1 for inv in invoices if inv["status"] != "SETTLED")
    settled = sum(1 for inv in invoices if inv["status"] == "SETTLED")
    return total, outstanding, settled
