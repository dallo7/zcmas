import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("CAPITALPAY_MODE", "mock")

from services.db import connect
from services.repository import (
    BL_CANCEL_REASONS,
    BlNumberConflict,
    bootstrap,
    cancel_bl_for_reupload,
    create_bl,
    display_bl_number,
    find_bl_number_conflict,
)


def _cleanup_bl(bl_number: str) -> None:
    with connect() as conn:
        for row in conn.execute(
            "SELECT id, bl_number FROM bills_of_lading WHERE bl_number = ? OR bl_number LIKE ?",
            (bl_number, f"{bl_number}%"),
        ).fetchall():
            bl_id = row[0]
            for (reviewed_id,) in conn.execute("SELECT id FROM reviewed_bls WHERE bl_id = ?", (bl_id,)).fetchall():
                for (inv_id,) in conn.execute("SELECT id FROM invoices WHERE reviewed_bl_id = ?", (reviewed_id,)).fetchall():
                    conn.execute("DELETE FROM payments WHERE invoice_id = ?", (inv_id,))
                    conn.execute("DELETE FROM invoices WHERE id = ?", (inv_id,))
                conn.execute("DELETE FROM z_sads WHERE reviewed_bl_id = ?", (reviewed_id,))
                conn.execute("DELETE FROM reviewed_bls WHERE id = ?", (reviewed_id,))
            conn.execute("DELETE FROM cargo_items WHERE bl_id = ?", (bl_id,))
            conn.execute("DELETE FROM bills_of_lading WHERE id = ?", (bl_id,))
        conn.commit()


def test_cancel_bl_allows_reupload():
    bl_number = "BL-CANCEL-REUPLOAD-001"
    bootstrap()
    _cleanup_bl(bl_number)

    create_bl(
        {
            "bl_number": bl_number,
            "doc_type": "Bill of Lading",
            "route_type": "Import",
            "transport_mode": "Sea",
            "zra_regime": "IM4 Home Use",
            "consignee_name": "Cancel Test",
            "gross_weight": 5,
            "no_containers": 1,
            "cargo_description": "Test",
            "gn83_category": "20FT_CONTAINER",
        },
        auto_review=True,
        use_ocr_defaults=False,
    )

    conflict = find_bl_number_conflict(bl_number)
    assert conflict is not None
    assert conflict.get("z_sad_number")

    try:
        create_bl({"bl_number": bl_number, "doc_type": "Bill of Lading"}, auto_review=False, use_ocr_defaults=False)
        raised = False
    except BlNumberConflict:
        raised = True
    assert raised

    cancelled = cancel_bl_for_reupload(conflict["id"], BL_CANCEL_REASONS[0])
    assert cancelled["status"] == "CANCELLED"
    assert display_bl_number(cancelled) == bl_number

    assert find_bl_number_conflict(bl_number) is None

    bl2 = create_bl(
        {
            "bl_number": bl_number,
            "doc_type": "Bill of Lading",
            "route_type": "Import",
            "transport_mode": "Sea",
            "zra_regime": "IM4 Home Use",
            "consignee_name": "Re-upload",
            "gross_weight": 6,
            "no_containers": 1,
            "cargo_description": "Test 2",
            "gn83_category": "20FT_CONTAINER",
        },
        auto_review=True,
        use_ocr_defaults=False,
    )
    assert bl2["bl_number"] == bl_number
    assert bl2["status"] != "CANCELLED"
