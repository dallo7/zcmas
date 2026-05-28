"""End-to-end: CapitalPay BL variants -> upload -> Z-SAD -> invoice -> PDF download."""

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
from services.ocr import extract_bl_fields, extract_text_pdf, parse_bl_text
from services.db import connect
from services.repository import (
    bootstrap,
    create_bl,
    generate_invoice,
    get_reviewed_bl,
    list_invoices,
    list_reviewed_bls,
    authenticate_user,
)


def _cleanup_capitalpay_test_bls(bl_numbers: list[str]) -> None:
    with connect() as conn:
        for bl_number in bl_numbers:
            bl = conn.execute(
                "SELECT id FROM bills_of_lading WHERE bl_number = ?", (bl_number,)
            ).fetchone()
            if not bl:
                continue
            bl_id = bl[0]
            reviewed = conn.execute(
                "SELECT id FROM reviewed_bls WHERE bl_id = ?", (bl_id,)
            ).fetchall()
            for (reviewed_id,) in reviewed:
                invoices = conn.execute(
                    "SELECT id FROM invoices WHERE reviewed_bl_id = ?", (reviewed_id,)
                ).fetchall()
                for (invoice_id,) in invoices:
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

BL_CASES = [
    {
        "fixture": "BL2_2Containers_MAERSK_MAEU0662766336.txt",
        "pdf": "BL2_2Containers_MAERSK_MAEU0662766336.pdf",
        "bl_number": "MAEU0662766336",
        "no_containers": 2,
        "gross_weight": 54.13,
        "gn83_category": "20FT_CONTAINER",
        "cargo_contains": "RICE",
    },
    {
        "fixture": "BL3_3Containers_1Loose_CMA CGM_CMAU1839718662.txt",
        "pdf": "BL3_3Containers_1Loose_CMA CGM_CMAU1839718662.pdf",
        "bl_number": "CMAU1839718662",
        "no_containers": 3,
        "gross_weight": 96.345,
        "gn83_category": "LOOSE_LCL",
        "cargo_contains": "RICE",
    },
    {
        "fixture": "BL5_4LCL_1Container_EVERGREEN_EITU7350316991.txt",
        "pdf": "BL5_4LCL_1Container_EVERGREEN_EITU7350316991.pdf",
        "bl_number": "EITU7350316991",
        "no_containers": 1,
        "gross_weight": 47.865,
        "gn83_category": "LOOSE_LCL",
        "cargo_contains": "RICE",
    },
]


@pytest.mark.parametrize("case", BL_CASES, ids=[c["bl_number"] for c in BL_CASES])
def test_parse_capitalpay_bl_fixture(case):
    text = (FIXTURES / case["fixture"]).read_text(encoding="utf-8", errors="replace")
    parsed = parse_bl_text(text)
    assert parsed["bl_number"] == case["bl_number"]
    assert parsed["consignee_name"] == "ETS ARAKA"
    assert parsed["no_containers"] == case["no_containers"]
    assert parsed["gross_weight"] == case["gross_weight"]
    assert parsed["gn83_category"] == case["gn83_category"]
    assert case["cargo_contains"] in (parsed.get("cargo_description") or "").upper()


@pytest.mark.parametrize("case", BL_CASES, ids=[c["bl_number"] for c in BL_CASES])
def test_extract_bl_fields_from_pdf_when_available(case):
    pdf_path = DOWNLOADS / case["pdf"]
    if not pdf_path.is_file():
        pytest.skip(f"PDF not on disk: {pdf_path}")
    text = extract_text_pdf(pdf_path)
    assert case["bl_number"] in text
    with patch.dict(os.environ, {"OCR_PROVIDER": "mock"}, clear=False):
        result = extract_bl_fields(str(pdf_path))
    assert result["bl_number"] == case["bl_number"]
    assert result["ocr_mode"] == "text_pdf"
    assert result["consignee_name"] == "ETS ARAKA"


@patch.dict(os.environ, {"CAPITALPAY_MODE": "mock"}, clear=False)
def test_e2e_bl_upload_zsad_invoice_pdf_download():
    bootstrap()
    _cleanup_capitalpay_test_bls([c["bl_number"] for c in BL_CASES])
    created_reviewed = []

    for case in BL_CASES:
        text = (FIXTURES / case["fixture"]).read_text(encoding="utf-8", errors="replace")
        parsed = parse_bl_text(text)
        bl = create_bl(
            {
                **parsed,
                "doc_type": "Bill of Lading",
                "route_type": "Import",
                "transport_mode": "Sea",
                "zra_regime": "IM4 Home Use",
                "file_name": case["pdf"],
            },
            auto_review=True,
            use_ocr_defaults=False,
        )
        reviewed = bl["reviewed_bl"]
        created_reviewed.append(reviewed["id"])
        assert reviewed.get("z_sad_number", "").startswith("Z-SAD-")
        assert bl["bl_number"] == case["bl_number"]

        reviewed_row = get_reviewed_bl(reviewed["id"])
        assert reviewed_row["bl_number"] == case["bl_number"]
        assert reviewed_row["status"] in {"REVIEWED_ZSAD_ISSUED", "AWAITING_PAYMENT"}

        invoice = generate_invoice(
            reviewed["id"],
            "SERVICE_FEE_ONLY",
            contact_phone="0971234567",
            contact_email="importer@example.com",
        )
        assert invoice["capitalpay_urn"].startswith("CPAY")
        assert invoice["bl_number"] == case["bl_number"]
        assert invoice.get("pdf_path")
        assert Path(invoice["pdf_path"]).is_file()
        assert Path(invoice["pdf_path"]).read_bytes()[:4] == b"%PDF"

        client = server.test_client()
        user = authenticate_user("companyadmin", "demo123")
        assert user
        auth.install_client_session(client, user)
        response = client.get(f"/download/invoice/{invoice['id']}.pdf")
        assert response.status_code == 200
        assert response.mimetype == "application/pdf"
        assert response.data[:4] == b"%PDF"

    assert len(list_reviewed_bls()) >= len(BL_CASES)
    assert len(list_invoices()) >= len(BL_CASES)
