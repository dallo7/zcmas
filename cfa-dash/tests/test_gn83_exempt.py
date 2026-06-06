"""GN 83 G-03 sensitive product exemptions — Z-SAD without settlement charge."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("CAPITALPAY_MODE", "mock")

from services.db import connect
from services.gn83 import gn83_quote_for_reviewed, is_gn83_exempt, lookup_fee
from services.ocr import infer_gn83_category
from services.repository import bootstrap, create_bl, generate_invoice, get_reviewed_bl, issue_cargo_release, review_bl


def _cleanup_bl(bl_number: str) -> None:
    with connect() as conn:
        bl = conn.execute("SELECT id FROM bills_of_lading WHERE bl_number = ?", (bl_number,)).fetchone()
        if not bl:
            return
        bl_id = bl[0]
        for (reviewed_id,) in conn.execute("SELECT id FROM reviewed_bls WHERE bl_id = ?", (bl_id,)).fetchall():
            for (invoice_id,) in conn.execute(
                "SELECT id FROM invoices WHERE reviewed_bl_id = ?", (reviewed_id,)
            ).fetchall():
                conn.execute("DELETE FROM payments WHERE invoice_id = ?", (invoice_id,))
                conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
            conn.execute("DELETE FROM z_sads WHERE reviewed_bl_id = ?", (reviewed_id,))
            conn.execute("DELETE FROM reviewed_bls WHERE id = ?", (reviewed_id,))
        conn.execute("DELETE FROM cargo_items WHERE bl_id = ?", (bl_id,))
        conn.execute("DELETE FROM bills_of_lading WHERE id = ?", (bl_id,))
        conn.commit()


@pytest.mark.parametrize(
    "category",
    ["FERTILIZER", "PETROLEUM", "SUGAR", "IN_HOUSE_CLEARANCE"],
)
def test_exempt_categories_have_zero_fee(category):
    assert is_gn83_exempt(category)
    assert lookup_fee("Import", "Sea", category, no_containers=2, gross_weight=120) == 0.0


@pytest.mark.parametrize(
    "text,expected",
    [
        ("UREA FERTILIZER BAGS", "FERTILIZER"),
        ("DIESEL FUEL IMPORT", "PETROLEUM"),
        ("RAW SUGAR BULK", "SUGAR"),
        ("IN-HOUSE CLEARANCE ARRANGEMENT", "IN_HOUSE_CLEARANCE"),
    ],
)
def test_ocr_infers_exempt_categories(text, expected):
    assert infer_gn83_category(text, {"cargo_description": text}) == expected


def test_exempt_bl_issues_zsad_without_invoice():
    bootstrap()
    bl_number = "EXEMPT-FERT-001"
    _cleanup_bl(bl_number)
    bl = create_bl(
        {
            "bl_number": bl_number,
            "doc_type": "Bill of Lading",
            "route_type": "Import",
            "transport_mode": "Sea",
            "zra_regime": "IM4 Home Use",
            "consignee_name": "Exempt Importer",
            "consignee_tin": "1000999001",
            "cargo_description": "UREA fertiliser",
            "gn83_category": "FERTILIZER",
            "gn83_unit": "Exempt",
            "gn83_fee_usd": 0,
            "no_containers": 1,
            "gross_weight": 24,
            "file_name": "exempt.pdf",
        },
        auto_review=True,
        use_ocr_defaults=False,
    )
    reviewed = bl["reviewed_bl"]
    assert reviewed.get("z_sad_number")
    quote = gn83_quote_for_reviewed(get_reviewed_bl(reviewed["id"]))
    assert quote["exempt"] is True
    assert quote["std_min_fee"] == 0.0
    with pytest.raises(ValueError, match="GN 83 exempt"):
        generate_invoice(reviewed["id"], "FULL_SETTLEMENT")
    issue_cargo_release(reviewed["id"])
    assert get_reviewed_bl(reviewed["id"])["status"] == "CARGO_RELEASED"
    _cleanup_bl(bl_number)
