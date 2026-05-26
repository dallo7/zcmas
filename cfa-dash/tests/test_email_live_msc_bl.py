"""
Live integration: MSC BL -> invoice PDF -> Bird email + WhatsApp to cwakhusama@gmail.com.

Skipped unless BIRD_EMAIL_MODE=api and BIRD_EMAIL_ACCESS_KEY are set.
Run: pytest tests/test_email_live_msc_bl.py -v -s
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BL_PDF = Path(
    r"c:\Users\cwakh\Downloads\CapitalPay_BLs_TestDocs\CapitalPay_BLs\R_saidi\BL1_1Container_MSC_MSC0620430218.pdf"
)
CLIENT_EMAIL = "cwakhusama@gmail.com"
CLIENT_PHONE = "0977123456"

pytestmark = pytest.mark.skipif(
    os.getenv("BIRD_EMAIL_MODE", "mock").lower() != "api" or not os.getenv("BIRD_EMAIL_ACCESS_KEY"),
    reason="Set BIRD_EMAIL_MODE=api and BIRD_EMAIL_ACCESS_KEY in .env for live Bird email test",
)


@pytest.fixture(scope="module")
def bl_invoice():
    from services.db import connect
    from services.ocr import extract_bl_fields
    from services.repository import bootstrap, create_bl, generate_invoice, share_invoice_with_importer

    if not BL_PDF.is_file():
        pytest.skip(f"BL PDF not found: {BL_PDF}")

    bootstrap()

    extracted = extract_bl_fields(str(BL_PDF))
    bl_number = extracted.get("bl_number") or "MSC0620430218"

    with connect() as conn:
        existing = conn.execute("SELECT id FROM bills_of_lading WHERE bl_number = ?", (bl_number,)).fetchone()
        if existing:
            bl_id = existing[0]
            reviewed = conn.execute("SELECT id FROM reviewed_bls WHERE bl_id = ?", (bl_id,)).fetchone()
            if reviewed:
                for (inv_id,) in conn.execute(
                    "SELECT id FROM invoices WHERE reviewed_bl_id = ?", (reviewed[0],)
                ).fetchall():
                    conn.execute("DELETE FROM payments WHERE invoice_id = ?", (inv_id,))
                    conn.execute("DELETE FROM invoices WHERE id = ?", (inv_id,))
                conn.execute("DELETE FROM z_sads WHERE reviewed_bl_id = ?", (reviewed[0],))
                conn.execute("DELETE FROM reviewed_bls WHERE id = ?", (reviewed[0],))
            conn.execute("DELETE FROM cargo_items WHERE bl_id = ?", (bl_id,))
            conn.execute("DELETE FROM bills_of_lading WHERE id = ?", (bl_id,))
            conn.commit()

    payload = {
        **extracted,
        "bl_number": bl_number,
        "doc_type": "Bill of Lading",
        "route_type": extracted.get("route_type") or "Import",
        "transport_mode": extracted.get("transport_mode") or "Sea",
        "zra_regime": "IM4 Home Use",
        "file_name": BL_PDF.name,
        "file_path": str(BL_PDF),
        "gn83_category": extracted.get("gn83_category") or "20FT_CONTAINER",
        "no_containers": extracted.get("no_containers") or 1,
    }
    bl = create_bl(payload, auto_review=True, use_ocr_defaults=False)
    reviewed_id = bl["reviewed_bl"]["id"]
    invoice = generate_invoice(
        reviewed_id,
        "SERVICE_FEE_ONLY",
        contact_phone=CLIENT_PHONE,
        contact_email=CLIENT_EMAIL,
    )
    return invoice


def test_live_invoice_email_with_pdf_attachment(bl_invoice):
    from services.repository import share_invoice_with_importer

    shared = share_invoice_with_importer(
        bl_invoice["id"],
        channels=["EMAIL", "WHATSAPP"],
        contact_email=CLIENT_EMAIL,
    )
    assert shared["whatsapp"]["url"]
    assert "wa.me" in shared["whatsapp"]["url"]
    email = shared["email"]
    assert email.get("sent") is True, email.get("reason") or email
    assert email.get("mode") == "bird"
    print(f"Email sent to {CLIENT_EMAIL} for invoice {bl_invoice['invoice_number']}")


def test_live_plain_bird_ping():
    from services.messaging import send_email

    result = send_email(
        CLIENT_EMAIL,
        "ZCAMS Bird API test",
        "This is a connectivity test from ZCAMS.",
        recipient_name="ZCAMS Test",
        description="ZCAMS connectivity test",
    )
    assert result.get("sent") is True, result
