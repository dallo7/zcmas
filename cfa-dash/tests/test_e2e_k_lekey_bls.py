"""
End-to-end: k_lekey CapitalPay BL set -> OCR upload -> Z-SAD -> invoice -> share.

Run:
  pytest tests/test_e2e_k_lekey_bls.py -v -s

Requires PDFs under CapitalPay_BLs_TestDocs/CapitalPay_BLs/k_lekey/
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app import server
from services.gn83 import calculate_invoice, gn83_quote_for_reviewed
from services.ocr import extract_bl_fields
from services.repository import (
    bootstrap,
    create_bl,
    generate_invoice,
    get_reviewed_bl,
    share_invoice_with_importer,
)

K_LEKEY_DIR = Path(
    r"c:\Users\cwakh\Downloads\CapitalPay_BLs_TestDocs\CapitalPay_BLs\k_lekey"
)

CLIENT_EMAIL = os.getenv("ZCAMS_E2E_EMAIL", "cwakhusama@gmail.com")
CLIENT_PHONE = os.getenv("ZCAMS_E2E_PHONE", "0977123456")

# 2 × Service Fee Only, 3 × Full Settlement
BL_CASES = [
    ("BL1_1Container_MSC_MSC4051473322.pdf", "SERVICE_FEE_ONLY"),
    ("BL2_2Containers_MAERSK_MAEU5461108570.pdf", "SERVICE_FEE_ONLY"),
    ("BL3_3Containers_1Loose_CMA CGM_CMAU2023754313.pdf", "FULL_SETTLEMENT"),
    ("BL4_10Containers_HAPAG-LLOYD_HLCU1443330589.pdf", "FULL_SETTLEMENT"),
    ("BL5_4LCL_1Container_EVERGREEN_EITU7260197003.pdf", "FULL_SETTLEMENT"),
]

BENEFICIARY = {
    "beneficiary_name": "ETS ARAKA",
    "beneficiary_bank_name": "Stanbic Bank Zambia",
    "beneficiary_account_number": "9130000123456",
}


def _cleanup_bl(bl_number: str) -> None:
    from services.db import connect

    with connect() as conn:
        bl = conn.execute(
            "SELECT id FROM bills_of_lading WHERE bl_number = ?", (bl_number,)
        ).fetchone()
        if not bl:
            return
        bl_id = bl[0]
        for (reviewed_id,) in conn.execute(
            "SELECT id FROM reviewed_bls WHERE bl_id = ?", (bl_id,)
        ).fetchall():
            for (inv_id,) in conn.execute(
                "SELECT id FROM invoices WHERE reviewed_bl_id = ?", (reviewed_id,)
            ).fetchall():
                conn.execute("DELETE FROM payments WHERE invoice_id = ?", (inv_id,))
                conn.execute("DELETE FROM invoices WHERE id = ?", (inv_id,))
            conn.execute("DELETE FROM z_sads WHERE reviewed_bl_id = ?", (reviewed_id,))
            conn.execute("DELETE FROM reviewed_bls WHERE id = ?", (reviewed_id,))
        conn.execute("DELETE FROM cargo_items WHERE bl_id = ?", (bl_id,))
        conn.execute("DELETE FROM bills_of_lading WHERE id = ?", (bl_id,))
        conn.commit()


def _run_bl_e2e(pdf_name: str, invoice_type: str) -> dict:
    pdf_path = K_LEKEY_DIR / pdf_name
    if not pdf_path.is_file():
        pytest.skip(f"PDF not found: {pdf_path}")

    extracted = extract_bl_fields(str(pdf_path))
    bl_number = extracted.get("bl_number")
    assert bl_number, f"Could not parse BL number from {pdf_name}"

    _cleanup_bl(bl_number)

    payload = {
        **extracted,
        "bl_number": bl_number,
        "doc_type": "Bill of Lading",
        "route_type": extracted.get("route_type") or "Import",
        "transport_mode": extracted.get("transport_mode") or "Sea",
        "zra_regime": "IM4 Home Use",
        "file_name": pdf_name,
        "file_path": str(pdf_path),
        "gn83_category": extracted.get("gn83_category") or "20FT_CONTAINER",
        "no_containers": extracted.get("no_containers") or 1,
    }

    bl = create_bl(payload, auto_review=True, use_ocr_defaults=False)
    reviewed = bl["reviewed_bl"]
    assert reviewed.get("z_sad_number", "").startswith("Z-SAD-")

    reviewed_row = get_reviewed_bl(reviewed["id"])
    quote = gn83_quote_for_reviewed(reviewed_row)
    calc = calculate_invoice(quote["std_min_fee"], invoice_type)

    inv_kwargs = {
        "contact_phone": CLIENT_PHONE,
        "contact_email": CLIENT_EMAIL,
    }
    if invoice_type == "FULL_SETTLEMENT":
        inv_kwargs.update(BENEFICIARY)

    invoice = generate_invoice(reviewed["id"], invoice_type, **inv_kwargs)

    shared = share_invoice_with_importer(
        invoice["id"],
        channels=["EMAIL", "WHATSAPP"],
        contact_email=CLIENT_EMAIL,
    )

    client = server.test_client()
    pdf_resp = client.get(f"/download/invoice/{invoice['id']}.pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.data[:4] == b"%PDF"

    email = shared.get("email", {})
    whatsapp = shared.get("whatsapp", {})

    assert float(invoice.get("total") or 0) == calc["total"]
    assert float(invoice.get("total") or 0) > 0

    return {
        "pdf_file": pdf_name,
        "invoice_type": invoice_type,
        "bl_number": bl_number,
        "containers": extracted.get("no_containers"),
        "gn83_category": quote.get("category"),
        "std_min_fee": quote["std_min_fee"],
        "invoice_total": calc["total"],
        "payable_amount": invoice.get("payable_amount") or invoice.get("total"),
        "z_sad_number": reviewed_row["z_sad_number"],
        "invoice_number": invoice["invoice_number"],
        "capitalpay_urn": invoice.get("capitalpay_urn"),
        "email_sent": email.get("sent"),
        "email_mode": email.get("mode"),
        "whatsapp_url": whatsapp.get("url"),
    }


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_db():
    bootstrap()
    yield


@pytest.mark.parametrize(
    "pdf_name,invoice_type",
    BL_CASES,
    ids=[f"{p.replace('.pdf', '')}-{t}" for p, t in BL_CASES],
)
def test_k_lekey_bl_full_pipeline(pdf_name, invoice_type):
    """Upload BL PDF -> review + Z-SAD -> invoice -> share -> PDF download."""
    result = _run_bl_e2e(pdf_name, invoice_type)
    assert result["capitalpay_urn"]
    assert str(result["capitalpay_urn"]).startswith("CPAY")
    assert result["whatsapp_url"] and "wa.me" in result["whatsapp_url"]
    assert result["invoice_total"] == result["payable_amount"]
    assert result["invoice_total"] > 0

    print(
        f"\n=== {result['pdf_file']} ===\n"
        f"  Type: {result['invoice_type']} | BL: {result['bl_number']} | containers: {result['containers']} | GN83: {result['gn83_category']}\n"
        f"  Z-SAD: {result['z_sad_number']}\n"
        f"  Invoice: {result['invoice_number']} | CPAY: {result['capitalpay_urn']}\n"
        f"  Std min: USD {result['std_min_fee']:,.2f} | Total: USD {result['invoice_total']:,.2f}\n"
        f"  Email: sent={result['email_sent']} mode={result['email_mode']} -> {CLIENT_EMAIL}\n"
        f"  WhatsApp: {result['whatsapp_url'][:80]}..."
    )

