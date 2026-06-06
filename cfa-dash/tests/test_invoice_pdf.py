import os
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("CAPITALPAY_MODE", "mock")

from services.pdf_service import AUTHORISED_COLLECTION_BANK_LOGOS, generate_invoice_pdf
from services.repository import bootstrap, generate_invoice, get_company, invoice_pay_url, list_reviewed_bls


def test_authorised_collection_bank_logos_present():
    for logo_path in AUTHORISED_COLLECTION_BANK_LOGOS:
        assert logo_path.is_file(), f"Missing bank logo asset: {logo_path}"


@patch.dict(os.environ, {"CAPITALPAY_MODE": "mock"}, clear=False)
def test_generate_invoice_pdf_file():
    bootstrap()
    reviewed = list_reviewed_bls()[0]
    invoice = generate_invoice(
        reviewed["id"],
        "FULL_SETTLEMENT",
        contact_phone="0971234567",
        contact_email="importer@example.com",
    )
    path = Path(invoice["pdf_path"])
    assert path.is_file()
    assert path.stat().st_size > 1500
    content = path.read_bytes()
    assert content[:4] == b"%PDF"
    assert float(invoice.get("total") or 0) > 0


def test_generate_invoice_pdf_amount_from_total_or_payable():
    """Regression: draft omitted total — PDF amount must not be zero."""
    path = generate_invoice_pdf(
        {
            "id": "inv-regression",
            "invoice_number": "INV-REGRESSION",
            "invoice_type": "FULL_SETTLEMENT",
            "capitalpay_urn": "CPAYREGTEST",
            "payable_amount": 35.0,
            "bl_number": "BL-REG",
            "z_sad_number": "Z-SAD-REG",
        },
        get_company(),
    )
    from services.pdf_service import _gn83_total

    assert _gn83_total({"payable_amount": 35.0}) == 35.0
    assert path.stat().st_size > 1500


def test_invoice_payment_link_uses_zcams_checkout(monkeypatch):
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    invoice = {
        "id": "inv-40713f4d6e51",
        "invoice_number": "INV-LINK-REGRESSION",
        "invoice_type": "FULL_SETTLEMENT",
        "capitalpay_urn": "CPAYMRWPAK",
        "checkout_url": "https://app.capitalpay.co.tz/pay/CPAYMRWPAK",
        "total": 35.0,
        "bl_number": "BL-LINK",
        "z_sad_number": "Z-SAD-LINK",
    }

    path = generate_invoice_pdf(invoice, get_company())
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)

    assert invoice_pay_url(invoice) == "http://127.0.0.1:8050/capitalpay/checkout/inv-40713f4d6e51"
    assert "http://127.0.0.1:8050/capitalpay/checkout/inv-40713f4d6e51" in text
    assert "https://app.capitalpay.co.tz/pay/CPAYMRWPAK" not in text
    assert "AUTHORISED COLLECTION BANKS" in text
    assert "ZNCOZMLU" not in text
    assert "SWIFT" not in text
