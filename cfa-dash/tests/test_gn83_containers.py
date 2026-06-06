"""GN 83 per-container billing and BL1/BL4 parsing."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("CAPITALPAY_MODE", "mock")

from app import server
from services import auth
from services.gn83 import calculate_invoice, gn83_quote_for_reviewed, lookup_fee
from services.ocr import extract_bl_fields, extract_text_pdf, parse_bl_text
from services.db import connect
from services.repository import bootstrap, create_bl, generate_invoice, get_reviewed_bl, authenticate_user


def _cleanup_bl(bl_numbers: list[str]) -> None:
    with connect() as conn:
        for bl_number in bl_numbers:
            bl = conn.execute(
                "SELECT id FROM bills_of_lading WHERE bl_number = ?", (bl_number,)
            ).fetchone()
            if not bl:
                continue
            bl_id = bl[0]
            for (reviewed_id,) in conn.execute(
                "SELECT id FROM reviewed_bls WHERE bl_id = ?", (bl_id,)
            ).fetchall():
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


FIXTURES = Path(__file__).resolve().parent / "fixtures"
DOWNLOADS = Path(
    r"c:\Users\cwakh\Downloads\CapitalPay_BLs_TestDocs\CapitalPay_BLs\j_patrick"
)

BL1 = {
    "fixture": "BL1_1Container_MSC_MSC8466112528.txt",
    "pdf": "BL1_1Container_MSC_MSC8466112528.pdf",
    "bl_number": "MSC8466112528",
    "containers": 1,
    "std_min": 150.0,
    "full_total": 209.0,
}
BL4 = {
    "fixture": "BL4_10Containers_HAPAG-LLOYD_HLCU9507597961.txt",
    "pdf": "BL4_10Containers_HAPAG-LLOYD_HLCU9507597961.pdf",
    "bl_number": "HLCU9507597961",
    "containers": 10,
    "std_min": 1500.0,
    "full_total": 2088.0,
}


def test_lookup_fee_multiplies_per_container():
    assert lookup_fee("Import", "Sea", "20FT_CONTAINER", quantity=10) == 1500.0
    assert lookup_fee("Import", "Sea", "20FT_CONTAINER", no_containers=10) == 1500.0
    assert lookup_fee("Import", "Sea", "LOOSE_LCL", no_containers=10) == 90.0


def test_calculate_invoice_uses_twenty_percent_admin_and_sixteen_vat():
    full = calculate_invoice(1500.0, "FULL_SETTLEMENT")
    assert full == {"std_min_fee": 1500.0, "admin_fee": 300.0, "vat": 288.0, "total": 2088.0}


def test_calculate_invoice_single_20ft_container():
    full = calculate_invoice(150.0, "FULL_SETTLEMENT")
    assert full == {"std_min_fee": 150.0, "admin_fee": 30.0, "vat": 28.8, "total": 209.0}


@pytest.mark.parametrize("case", [BL1, BL4], ids=["MSC8466112528", "HLCU9507597961"])
def test_parse_bl_fixture(case):
    text = (FIXTURES / case["fixture"]).read_text(encoding="utf-8", errors="replace")
    if not (FIXTURES / case["fixture"]).is_file():
        pytest.skip("fixture missing")
    parsed = parse_bl_text(text)
    assert parsed["bl_number"] == case["bl_number"]
    assert parsed["no_containers"] == case["containers"]
    assert parsed["gn83_category"] == "20FT_CONTAINER"


@patch.dict(os.environ, {"CAPITALPAY_MODE": "mock"}, clear=False)
def test_e2e_ten_container_invoice_amounts():
    bootstrap()
    _cleanup_bl([BL4["bl_number"], BL1["bl_number"]])
    text = (FIXTURES / BL4["fixture"]).read_text(encoding="utf-8", errors="replace")
    parsed = parse_bl_text(text)
    bl = create_bl(
        {**parsed, "doc_type": "Bill of Lading", "route_type": "Import", "transport_mode": "Sea", "zra_regime": "IM4 Home Use"},
        auto_review=True,
        use_ocr_defaults=False,
    )
    reviewed = get_reviewed_bl(bl["reviewed_bl"]["id"])
    quote = gn83_quote_for_reviewed(reviewed)
    assert quote["std_min_fee"] == BL4["std_min"]
    assert quote["units"] == 10

    full_inv = generate_invoice(
        reviewed["id"],
        "FULL_SETTLEMENT",
        contact_phone="0971234567",
        beneficiary_name="ETS ARAKA",
        beneficiary_bank_name="Stanbic",
        beneficiary_account_number="1234567890",
    )
    reviewed_id = reviewed["id"]
    assert full_inv["std_min_fee"] == 1500.0
    assert full_inv["admin_fee"] == 300.0
    assert full_inv["total"] == 2088.0

    repeat_full_inv = generate_invoice(
        reviewed_id,
        "FULL_SETTLEMENT",
        contact_phone="0971234567",
        beneficiary_name="ETS ARAKA",
        beneficiary_bank_name="Stanbic",
        beneficiary_account_number="1234567890",
    )
    assert repeat_full_inv["total"] == 2088.0

    client = server.test_client()
    user = authenticate_user("companyadmin", "demo123")
    assert user
    auth.install_client_session(client, user)
    assert client.get(f"/download/invoice/{full_inv['id']}.pdf").status_code == 200


def test_extract_bl1_pdf_when_available():
    pdf = DOWNLOADS / BL1["pdf"]
    if not pdf.is_file():
        pytest.skip("BL1 PDF not on disk")
    with patch.dict(os.environ, {"OCR_PROVIDER": "mock"}, clear=False):
        result = extract_bl_fields(str(pdf))
    assert result["bl_number"] == BL1["bl_number"]
    assert result["no_containers"] == 1
    assert result["ocr_mode"] == "text_pdf"
