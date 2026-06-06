from __future__ import annotations

import math
from typing import Any


GN83_FEES: dict[str, dict[str, dict[str, tuple[str, float]]]] = {
    "Import": {
        "Sea": {
            "20FT_CONTAINER": ("20-foot shipping container", 150.00),
            "40FT_CONTAINER": ("40-foot shipping container", 200.00),
            "DRY_BULK": ("Dry bulk cargo", 0.60),
            "BULK_LIQUID": ("Bulk liquid", 0.60),
            "MOTOR_VEHICLE": ("Motor vehicle", 130.00),
            "HEAVY_EQUIPMENT": ("Heavy machines & equipment", 250.00),
            "LIVE_ANIMAL": ("Live animal", 90.00),
            "LOOSE_LCL": ("Loose cargo / LCL", 90.00),
            "POST_ENTRY": ("Post entry & ex-bond", 60.00),
            "COASTWISE": ("Carriage coastwise transire", 90.00),
        },
        "Road": {
            "20FT_CONTAINER": ("20-foot shipping container", 130.00),
            "40FT_CONTAINER": ("40-foot shipping container", 190.00),
            "MOTOR_VEHICLE": ("Motor vehicle", 130.00),
            "HEAVY_EQUIPMENT": ("Heavy machines & equipment", 250.00),
            "LIVE_ANIMAL": ("Live animal", 60.00),
            "LOOSE_LCL": ("Loose cargo / LCL", 60.00),
        },
        "Air": {
            "PARCEL": ("Parcel / couriers", 60.00),
            "GENERAL_CARGO": ("General cargo", 90.00),
            "LIVE_ANIMAL": ("Live animal", 60.00),
        },
    },
    "Export": {
        "Sea": {
            "20FT_CONTAINER": ("20-foot shipping container", 150.00),
            "40FT_CONTAINER": ("40-foot shipping container", 200.00),
            "DRY_BULK": ("Dry bulk cargo", 0.60),
            "BULK_LIQUID": ("Bulk liquid", 0.60),
            "MOTOR_VEHICLE": ("Motor vehicle", 130.00),
            "HEAVY_EQUIPMENT": ("Heavy machines & equipment", 250.00),
            "LIVE_ANIMAL": ("Live animal", 90.00),
            "LOOSE_LCL": ("Loose cargo / LCL", 90.00),
            "COASTWISE": ("Carriage coastwise transire", 90.00),
        },
        "Road": {
            "20FT_CONTAINER": ("20-foot shipping container", 130.00),
            "40FT_CONTAINER": ("40-foot shipping container", 190.00),
            "MOTOR_VEHICLE": ("Motor vehicle", 130.00),
            "HEAVY_EQUIPMENT": ("Heavy machines & equipment", 250.00),
            "LIVE_ANIMAL": ("Live animal", 60.00),
            "LOOSE_LCL": ("Loose cargo / LCL", 60.00),
        },
        "Air": {
            "PARCEL": ("Parcel / couriers", 60.00),
            "GENERAL_CARGO": ("General cargo", 90.00),
            "PRECIOUS_MINERALS": ("Precious metal / minerals", 130.00),
            "LIVE_ANIMAL": ("Live animal", 60.00),
        },
    },
    "Transit": {
        "Sea": {
            "20FT_CONTAINER": ("20-foot shipping container", 200.00),
            "40FT_CONTAINER": ("40-foot shipping container", 250.00),
            "DRY_BULK": ("Dry bulk cargo", 0.50),
            "BULK_LIQUID": ("Bulk liquid", 0.50),
            "MOTOR_VEHICLE": ("Motor vehicle", 130.00),
            "HEAVY_EQUIPMENT": ("Heavy machines & equipment", 250.00),
            "LIVE_ANIMAL": ("Live animal", 130.00),
            "LOOSE_LCL": ("Loose cargo / LCL", 130.00),
        },
        "Road": {
            "20FT_CONTAINER": ("20-foot shipping container", 210.00),
            "40FT_CONTAINER": ("40-foot shipping container", 250.00),
            "MOTOR_VEHICLE": ("Motor vehicle", 130.00),
            "HEAVY_EQUIPMENT": ("Heavy machines & equipment", 250.00),
            "LIVE_ANIMAL": ("Live animal", 90.00),
            "LOOSE_LCL": ("Loose cargo / LCL", 90.00),
        },
        "Air": {
            "GENERAL_CARGO": ("General cargo", 130.00),
        },
    },
}

# GN 83 standard minimum applies per container (or per billable unit) for these categories.
PER_CONTAINER_CATEGORIES = {
    "20FT_CONTAINER",
    "40FT_CONTAINER",
    "MOTOR_VEHICLE",
    "HEAVY_EQUIPMENT",
    "LIVE_ANIMAL",
}

ADMIN_RATE = 0.20
VAT_RATE = 0.16

# GN 83 G-03 — sensitive product exemptions (Z-SAD still required; no GN 83 charge).
EXEMPT_GN83_CATEGORIES: dict[str, str] = {
    "FERTILIZER": "Fertiliser",
    "PETROLEUM": "Petroleum products",
    "SUGAR": "Sugar",
    "IN_HOUSE_CLEARANCE": "In-house clearance",
}


def is_gn83_exempt(category: str | None) -> bool:
    return (category or "") in EXEMPT_GN83_CATEGORIES


def exempt_category_label(category: str | None) -> str:
    return EXEMPT_GN83_CATEGORIES.get(category or "", category or "")


def all_category_options() -> list[dict]:
    """Dropdown options for BL capture — exempt categories first, then schedule rates."""
    options = [
        {"value": key, "label": f"{label} — GN 83 exempt (no charge)"}
        for key, label in EXEMPT_GN83_CATEGORIES.items()
    ]
    seen = set(EXEMPT_GN83_CATEGORIES)
    for route_modes in GN83_FEES.values():
        for fees in route_modes.values():
            for key, (label, amount) in fees.items():
                if key in seen:
                    continue
                seen.add(key)
                suffix = " / container" if key in PER_CONTAINER_CATEGORIES else ""
                options.append({"value": key, "label": f"{label}{suffix} - ${amount:,.2f}"})
    return options


def _ceil_usd(amount: float) -> float:
    return float(math.ceil(amount - 1e-9))


def category_options(route_type: str = "Import", transport_mode: str = "Sea") -> list[dict]:
    fees = GN83_FEES.get(route_type, {}).get(_transport_key(transport_mode), {})
    options = []
    for key, (label, amount) in fees.items():
        suffix = " / container" if key in PER_CONTAINER_CATEGORIES else ""
        options.append({"value": key, "label": f"{label}{suffix} - ${amount:,.2f}"})
    return options


def fee_label(route_type: str, transport_mode: str, category: str) -> str:
    if is_gn83_exempt(category):
        return exempt_category_label(category)
    return GN83_FEES.get(route_type, {}).get(_transport_key(transport_mode), {}).get(category, (category, 0))[0]


def unit_fee(route_type: str, transport_mode: str, category: str) -> float:
    if is_gn83_exempt(category):
        return 0.0
    _label, amount = GN83_FEES.get(route_type, {}).get(_transport_key(transport_mode), {}).get(category, (category, 0.0))
    return round(float(amount), 2)


def unit_label(category: str | None) -> str:
    return {
        "20FT_CONTAINER": "Container",
        "40FT_CONTAINER": "Container",
        "DRY_BULK": "MT",
        "BULK_LIQUID": "MT",
        "MOTOR_VEHICLE": "Unit",
        "HEAVY_EQUIPMENT": "Unit",
        "LIVE_ANIMAL": "BL",
        "LOOSE_LCL": "BL",
        "POST_ENTRY": "BL",
        "COASTWISE": "Transire",
        "PARCEL": "AWB",
        "GENERAL_CARGO": "AWB",
        "PRECIOUS_MINERALS": "AWB",
        "FERTILIZER": "Exempt",
        "PETROLEUM": "Exempt",
        "SUGAR": "Exempt",
        "IN_HOUSE_CLEARANCE": "Exempt",
    }.get(category or "", "Unit")


def _transport_key(transport_mode: str | None) -> str:
    return "Road" if transport_mode == "Rail" else (transport_mode or "Sea")


def billable_units(
    category: str,
    *,
    no_containers: int | float | None = None,
    gross_weight: float | None = None,
    quantity: float | None = None,
) -> float:
    containers = int(no_containers or 0)
    qty = float(quantity or 1)
    if category in PER_CONTAINER_CATEGORIES:
        return float(max(containers, qty, 1))
    if category in {"DRY_BULK", "BULK_LIQUID"}:
        return max(float(gross_weight or 0), 1.0)
    return max(qty, 1.0)


def lookup_fee(
    route_type: str,
    transport_mode: str,
    category: str,
    quantity: float = 1,
    *,
    no_containers: int | float | None = None,
    gross_weight: float | None = None,
) -> float:
    if is_gn83_exempt(category):
        return 0.0
    amount = unit_fee(route_type, transport_mode, category)
    units = billable_units(
        category,
        no_containers=no_containers,
        gross_weight=gross_weight,
        quantity=quantity,
    )
    if category in PER_CONTAINER_CATEGORIES or category in {"DRY_BULK", "BULK_LIQUID"}:
        return round(amount * units, 2)
    return round(amount, 2)


def gn83_quote_for_reviewed(reviewed: dict) -> dict[str, Any]:
    cargo = (reviewed.get("cargo_items") or [{}])[0]
    category = cargo.get("gn83_category") or "MOTOR_VEHICLE"
    route_type = reviewed.get("route_type", "Import")
    transport_mode = reviewed.get("transport_mode", "Sea")
    units = billable_units(
        category,
        no_containers=reviewed.get("no_containers"),
        gross_weight=cargo.get("weight") or reviewed.get("gross_weight"),
        quantity=cargo.get("quantity"),
    )
    rate = unit_fee(route_type, transport_mode, category)
    std_min = lookup_fee(
        route_type,
        transport_mode,
        category,
        quantity=units,
        no_containers=reviewed.get("no_containers"),
        gross_weight=cargo.get("weight") or reviewed.get("gross_weight"),
    )
    exempt = is_gn83_exempt(category)
    return {
        "category": category,
        "category_label": fee_label(route_type, transport_mode, category),
        "units": units,
        "unit_rate": rate,
        "std_min_fee": 0.0 if exempt else std_min,
        "per_container": category in PER_CONTAINER_CATEGORIES,
        "exempt": exempt,
    }


def calculate_invoice(std_min_fee: float, invoice_type: str) -> dict[str, float]:
    """
    GN 83 invoice amounts (USD).

    Full Settlement uses the standard minimum plus 20% admin fee.
    VAT is 16% (Zambia) on the combined subtotal.

    Invoice total is rounded up to the next whole dollar.
    """
    std = round(float(std_min_fee or 0), 2)
    admin = round(std * ADMIN_RATE, 2)
    subtotal = round(std + admin, 2)
    vat = round(subtotal * VAT_RATE, 2)
    return {
        "std_min_fee": std,
        "admin_fee": admin,
        "vat": vat,
        "total": _ceil_usd(subtotal + vat),
    }
