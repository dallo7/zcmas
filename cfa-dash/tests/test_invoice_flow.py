import os
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("CAPITALPAY_MODE", "mock")

from services import capitalpay
from services.gn83 import calculate_invoice, lookup_fee
from services.repository import (
    bootstrap,
    create_bl,
    generate_invoice,
    get_reviewed_bl,
    invoice_share_message,
    invoice_whatsapp_link,
    list_reviewed_bls,
    review_bl,
    share_invoice_with_importer,
)


def _reviewed_target() -> dict:
    reviewed = list_reviewed_bls()
    if reviewed:
        return reviewed[0]
    bl = create_bl(
        {
            "bl_number": "BL-FLOW-TEST-001",
            "doc_type": "Bill of Lading",
            "route_type": "Import",
            "transport_mode": "Sea",
            "zra_regime": "IM4 Home Use",
            "consignee_name": "Flow Test Importer",
            "gross_weight": 10,
            "cargo_description": "Test cargo",
            "gn83_category": "MOTOR_VEHICLE",
        },
        auto_review=True,
    )
    return get_reviewed_bl(bl["reviewed_bl"]["id"])


@patch.dict(os.environ, {"CAPITALPAY_MODE": "mock"}, clear=False)
def test_capitalpay_sign_uses_cpays_format():
    signed = capitalpay.sign_invoice(
        "INV-TEST-1",
        100.0,
        calc={"std_min_fee": 100.0, "admin_fee": 20.0, "vat": 0.0, "total": 100.0},
    )
    assert signed["urn"].startswith("CPAYMOCK")
    assert signed["capitalpay_number"] == signed["urn"]


def test_invoice_amounts_for_both_settlement_modes():
    std = lookup_fee("Import", "Sea", "MOTOR_VEHICLE")
    service = calculate_invoice(std, "SERVICE_FEE_ONLY")
    full = calculate_invoice(std, "FULL_SETTLEMENT")
    assert service["total"] == 31.0
    assert full["total"] == 181.0


@patch.dict(os.environ, {"CAPITALPAY_MODE": "mock", "BIRD_EMAIL_MODE": "mock"}, clear=False)
@patch("services.repository.send_email")
def test_generate_and_share_invoice_links(mock_send_email):
    mock_send_email.return_value = {"sent": True, "mode": "bird", "status_code": 202}
    bootstrap()
    reviewed = _reviewed_target()
    invoice = generate_invoice(
        reviewed["id"],
        "SERVICE_FEE_ONLY",
        contact_phone="0971234567",
        contact_email="importer@example.com",
    )
    assert invoice["capitalpay_urn"].startswith("CPAY")
    pdf_path = invoice.get("pdf_path") or ""
    assert pdf_path.endswith(".pdf")
    assert Path(pdf_path).is_file()
    message = invoice_share_message(invoice)
    assert invoice["invoice_number"] in message
    assert invoice["capitalpay_urn"] in message

    wa_link = invoice_whatsapp_link(invoice["id"])
    assert "wa.me/260971234567" in wa_link
    assert "text=" in wa_link

    shared = share_invoice_with_importer(
        invoice["id"],
        channels=["WHATSAPP", "SMS", "EMAIL"],
        contact_email="importer@example.com",
    )
    assert shared["whatsapp"]["url"].startswith("https://wa.me/")
    assert shared["sms"]["url"].startswith("sms:")
    assert shared["email"]["sent"] is True
    mock_send_email.assert_called()
