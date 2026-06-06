import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("CAPITALPAY_MODE", "mock")

from unittest.mock import patch

from services.db import connect
from services.repository import (
    bootstrap,
    create_bl,
    detach_zsad,
    detach_zsad_for_reupload,
    generate_invoice,
    get_reviewed_bl,
    get_zsad_detach_preview,
    list_z_sad_history,
)


def _cleanup_bl(bl_number: str) -> None:
    with connect() as conn:
        bl = conn.execute("SELECT id FROM bills_of_lading WHERE bl_number = ?", (bl_number,)).fetchone()
        if not bl:
            return
        bl_id = bl[0]
        for (reviewed_id,) in conn.execute("SELECT id FROM reviewed_bls WHERE bl_id = ?", (bl_id,)).fetchall():
            for (inv_id,) in conn.execute("SELECT id FROM invoices WHERE reviewed_bl_id = ?", (reviewed_id,)).fetchall():
                conn.execute("DELETE FROM payments WHERE invoice_id = ?", (inv_id,))
                conn.execute("DELETE FROM invoices WHERE id = ?", (inv_id,))
            conn.execute("DELETE FROM z_sads WHERE reviewed_bl_id = ?", (reviewed_id,))
            conn.execute("DELETE FROM reviewed_bls WHERE id = ?", (reviewed_id,))
        conn.execute("DELETE FROM cargo_items WHERE bl_id = ?", (bl_id,))
        conn.execute("DELETE FROM bills_of_lading WHERE id = ?", (bl_id,))
        conn.commit()


def _fresh_reviewed(bl_number: str = "BL-DETACH-TEST-001"):
    bootstrap()
    _cleanup_bl(bl_number)
    bl = create_bl(
        {
            "bl_number": bl_number,
            "doc_type": "Bill of Lading",
            "route_type": "Import",
            "transport_mode": "Sea",
            "zra_regime": "IM4 Home Use",
            "consignee_name": "Detach Test",
            "gross_weight": 12,
            "no_containers": 1,
            "cargo_description": "Test",
            "gn83_category": "20FT_CONTAINER",
        },
        auto_review=True,
        use_ocr_defaults=False,
    )
    return get_reviewed_bl(bl["reviewed_bl"]["id"])


@patch.dict(os.environ, {"CAPITALPAY_MODE": "mock"}, clear=False)
def test_detach_cancels_invoice_and_issues_new_zsad():
    reviewed = _fresh_reviewed()
    first_zsad = reviewed["z_sad_number"]
    invoice = generate_invoice(reviewed["id"], "FULL_SETTLEMENT", contact_phone="0971111111")
    assert invoice["status"] == "AWAITING_PAYMENT"

    preview = get_zsad_detach_preview(reviewed["id"])
    assert preview["can_detach"] is True
    assert len(preview["open_invoices"]) == 1
    assert preview["current_zsad"] == first_zsad

    updated = detach_zsad(reviewed["id"])
    summary = updated["detach_summary"]
    assert summary["old_zsad"] == first_zsad
    assert summary["new_zsad"] != first_zsad
    assert summary["cancelled_count"] == 1
    assert updated["status"] == "REVIEWED_ZSAD_ISSUED"
    assert updated["z_sad_number"] == summary["new_zsad"]

    history = list_z_sad_history(reviewed["id"])
    assert len(history) == 2
    assert history[0]["z_sad_number"] == summary["new_zsad"]
    assert history[0]["is_active"] == 1
    assert history[1]["z_sad_number"] == first_zsad
    assert history[1]["is_active"] == 0

    preview_after = get_zsad_detach_preview(reviewed["id"])
    assert preview_after["open_invoices"] == []


@patch.dict(os.environ, {"CAPITALPAY_MODE": "mock"}, clear=False)
def test_detach_blocked_after_cargo_released():
    from services.repository import issue_cargo_release, settle_invoice

    reviewed = _fresh_reviewed("BL-DETACH-RELEASED-001")
    invoice = generate_invoice(reviewed["id"], "FULL_SETTLEMENT", contact_phone="0971222222")
    settle_invoice(invoice["id"])
    issue_cargo_release(reviewed["id"])

    preview = get_zsad_detach_preview(reviewed["id"])
    assert preview["can_detach"] is False

    try:
        detach_zsad(reviewed["id"])
        raised = False
    except ValueError as exc:
        raised = True
        assert "cargo release" in str(exc).lower()
    assert raised


@patch.dict(os.environ, {"CAPITALPAY_MODE": "mock"}, clear=False)
def test_detach_for_reupload_allows_awaiting_payment_and_cancels_journey():
    reviewed = _fresh_reviewed("BL-DETACH-REUPLOAD-001")
    first_zsad = reviewed["z_sad_number"]
    invoice = generate_invoice(reviewed["id"], "FULL_SETTLEMENT", contact_phone="0971333333")
    assert invoice["status"] == "AWAITING_PAYMENT"

    preview = get_zsad_detach_preview(reviewed["id"])
    assert preview["can_detach"] is True

    cancelled = detach_zsad_for_reupload(reviewed["id"])
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["detach_summary"]["old_zsad"] == first_zsad
    assert cancelled["detach_summary"]["new_zsad"] is None
    assert cancelled["detach_summary"]["cancelled_count"] == 1


@patch.dict(os.environ, {"CAPITALPAY_MODE": "mock"}, clear=False)
def test_detach_for_reupload_blocked_when_settled_release_pending():
    from services.repository import settle_invoice

    reviewed = _fresh_reviewed("BL-DETACH-RELEASE-PENDING-001")
    invoice = generate_invoice(reviewed["id"], "FULL_SETTLEMENT", contact_phone="0971444444")
    settle_invoice(invoice["id"])

    preview = get_zsad_detach_preview(reviewed["id"])
    assert preview["can_detach"] is False
    assert "release is pending" in preview["block_reason"].lower()

    try:
        detach_zsad_for_reupload(reviewed["id"])
        raised = False
    except ValueError as exc:
        raised = True
        assert "release is pending" in str(exc).lower()
    assert raised
