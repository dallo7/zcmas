from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("CAPITALPAY_MODE", "mock")
os.environ.setdefault("ZCAMS_ALLOW_MOCK_CAPITALPAY", "true")

from services import agentic_workflow, repository
from services.db import connect
from services.gn83 import lookup_fee
from services.ocr import extract_bl_fields, parse_bl_text


K_LEKEY = Path(r"c:\Users\cwakh\Downloads\CapitalPay_BLs_TestDocs\CapitalPay_BLs\k_lekey")
FIXTURES = Path(__file__).resolve().parent / "fixtures"

BL_CASES = [
    (
        K_LEKEY / "BL1_1Container_MSC_MSC4051473322.pdf",
        {
            "bl_number": "MSC4051473322",
            "no_containers": 1,
            "gross_weight": 27.065,
            "gn83_category": "20FT_CONTAINER",
            "service_total": 35.0,
        },
    ),
    (
        K_LEKEY / "BL4_10Containers_HAPAG-LLOYD_HLCU1443330589.pdf",
        {
            "bl_number": "HLCU1443330589",
            "no_containers": 10,
            "gross_weight": 270.65,
            "gn83_category": "20FT_CONTAINER",
            "service_total": 348.0,
        },
    ),
]


def _cleanup_bl(bl_numbers: list[str]) -> None:
    with connect() as conn:
        for bl_number in bl_numbers:
            bl = conn.execute("SELECT id FROM bills_of_lading WHERE bl_number = ?", (bl_number,)).fetchone()
            if not bl:
                continue
            bl_id = bl[0]
            for (reviewed_id,) in conn.execute("SELECT id FROM reviewed_bls WHERE bl_id = ?", (bl_id,)).fetchall():
                for (invoice_id,) in conn.execute("SELECT id FROM invoices WHERE reviewed_bl_id = ?", (reviewed_id,)).fetchall():
                    conn.execute("DELETE FROM payments WHERE invoice_id = ?", (invoice_id,))
                    conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
                conn.execute("DELETE FROM z_sads WHERE reviewed_bl_id = ?", (reviewed_id,))
                conn.execute("DELETE FROM reviewed_bls WHERE id = ?", (reviewed_id,))
            conn.execute("DELETE FROM cargo_items WHERE bl_id = ?", (bl_id,))
            conn.execute("DELETE FROM bills_of_lading WHERE id = ?", (bl_id,))
        conn.commit()


@pytest.mark.parametrize(("pdf", "expected"), BL_CASES, ids=["agentic-bl1", "agentic-bl4"])
def test_agentic_skill_pdf_memory(pdf, expected, monkeypatch):
    if not pdf.is_file():
        pytest.skip(f"PDF not on disk: {pdf}")
    monkeypatch.setenv("OCR_PROVIDER", "mock")
    extracted = extract_bl_fields(str(pdf))
    assert extracted["bl_number"] == expected["bl_number"]
    assert extracted["ocr_mode"] == "text_pdf"
    assert extracted["no_containers"] == expected["no_containers"]
    assert extracted["gross_weight"] == expected["gross_weight"]
    assert extracted["gn83_category"] == expected["gn83_category"]


def test_agentic_five_value_gate_blocks_before_send():
    data = agentic_workflow.five_value_snapshot(
        {},
        bl_number="MSC4051473322",
        consignee_tin="1000123456",
        gross_weight=27.065,
        no_containers=1,
        gn83_category="20FT_CONTAINER",
        invoice_type="SERVICE_FEE_ONLY",
    )
    with pytest.raises(ValueError, match="Confirm the five-value"):
        agentic_workflow.validate_five_values(
            data,
            confirmed=False,
            channels=["EMAIL", "WHATSAPP"],
            email="importer@example.com",
            phone="0971234567",
        )
    with pytest.raises(ValueError, match="Client phone"):
        agentic_workflow.validate_five_values(
            data,
            confirmed=True,
            channels=["WHATSAPP"],
            email=None,
            phone="",
        )


def test_agentic_lcl_guardrail_keeps_flat_gn83_fee():
    for fixture in [
        "BL3_3Containers_1Loose_CMA CGM_CMAU1839718662.txt",
        "BL5_4LCL_1Container_EVERGREEN_EITU7350316991.txt",
    ]:
        parsed = parse_bl_text((FIXTURES / fixture).read_text(encoding="utf-8", errors="replace"))
        assert parsed["gn83_category"] == "LOOSE_LCL"
        assert lookup_fee("Import", "Sea", "LOOSE_LCL", no_containers=parsed.get("no_containers")) == 90.0


def test_agentic_invoice_checkout_url_reuses_signed_capitalpay_ref():
    assert (
        agentic_workflow.invoice_checkout_url({"capitalpay_urn": "CPAYAGENTIC"})
        == "https://app.capitalpay.co.tz/pay/CPAYAGENTIC"
    )


def test_agentic_e2e_generates_zsad_invoice_and_share(monkeypatch):
    pdf, expected = BL_CASES[0]
    if not pdf.is_file():
        pytest.skip(f"PDF not on disk: {pdf}")
    monkeypatch.setenv("CAPITALPAY_MODE", "mock")
    monkeypatch.setenv("OCR_PROVIDER", "mock")
    monkeypatch.setattr(
        repository,
        "send_email",
        lambda *args, **kwargs: {"sent": True, "mode": "test"},
    )
    repository.bootstrap()
    _cleanup_bl([expected["bl_number"]])
    try:
        extracted = agentic_workflow.extract_agentic_bl(str(pdf))
        data = agentic_workflow.five_value_snapshot(
            extracted,
            bl_number=extracted["bl_number"],
            consignee_tin=extracted.get("consignee_tin") or "1000123456",
            gross_weight=extracted["gross_weight"],
            no_containers=extracted["no_containers"],
            gn83_category=extracted["gn83_category"],
            invoice_type="SERVICE_FEE_ONLY",
        )
        agentic_workflow.validate_five_values(
            data,
            confirmed=True,
            channels=["EMAIL", "WHATSAPP"],
            email="importer@example.com",
            phone="0971234567",
        )
        bl = agentic_workflow.create_agentic_bl(data)
        reviewed = agentic_workflow.issue_agentic_zsad(bl["id"])
        result = agentic_workflow.generate_and_share_agentic_invoice(
            reviewed["id"],
            invoice_type="SERVICE_FEE_ONLY",
            email="importer@example.com",
            phone="0971234567",
            channels=["EMAIL", "WHATSAPP"],
        )
        summary = agentic_workflow.summarize_result(result["invoice"], repository.get_reviewed_bl(reviewed["id"]), result["share_results"])
        assert summary["bl_number"] == expected["bl_number"]
        assert summary["z_sad_number"].startswith("Z-SAD-")
        assert summary["total"] == expected["service_total"]
        assert summary["capitalpay_ref"].startswith("CPAY")
        assert summary["payable_amount"] == expected["service_total"]
        assert summary["whatsapp_url"].startswith("https://wa.me/")
        assert summary["email"]["sent"] is True
        assert "download/invoice" in summary["pdf_url"]
        assert summary["pay_now_url"].startswith("https://app.capitalpay.co.tz/pay/")
    finally:
        _cleanup_bl([expected["bl_number"]])


def test_agentic_invoice_share_is_idempotent(monkeypatch):
    calls = {"invoice": 0, "share": 0}
    invoice = {
        "id": "inv-agentic-idem",
        "bl_number": "MSC4051473322",
        "z_sad_number": "Z-SAD-IDEM",
        "invoice_number": "INV-IDEM",
        "invoice_type": "SERVICE_FEE_ONLY",
        "total": 35.0,
        "std_min_fee": 150.0,
    }

    def fake_generate_invoice(*_args, **_kwargs):
        calls["invoice"] += 1
        return invoice

    def fake_share(*_args, **_kwargs):
        calls["share"] += 1
        return {"email": {"sent": True, "mode": "test"}, "whatsapp": {"url": "https://wa.me/260971234567"}}

    monkeypatch.setattr(repository, "generate_invoice", fake_generate_invoice)
    monkeypatch.setattr(repository, "share_invoice_with_importer", fake_share)

    first = agentic_workflow.generate_and_share_agentic_invoice(
        "reviewed-idem",
        invoice_type="SERVICE_FEE_ONLY",
        email="importer@example.com",
        phone="0971234567",
        channels=["EMAIL", "WHATSAPP"],
        idempotency_key="agentic-idem-key",
    )
    second = agentic_workflow.generate_and_share_agentic_invoice(
        "reviewed-idem",
        invoice_type="SERVICE_FEE_ONLY",
        email="importer@example.com",
        phone="0971234567",
        channels=["EMAIL", "WHATSAPP"],
        idempotency_key="agentic-idem-key",
    )

    assert first == second
    assert calls == {"invoice": 1, "share": 1}
