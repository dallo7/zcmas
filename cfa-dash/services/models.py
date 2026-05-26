from __future__ import annotations

from services.repository import money


def display_weight(value) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):,.2f} MT"
