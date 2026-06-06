"""
Live CapitalPay signing — requires CAPITALPAY_MODE=real and credentials in .env.

pytest tests/test_capitalpay_live_api.py -v -s
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

pytestmark = pytest.mark.skipif(
    os.getenv("CAPITALPAY_MODE", "mock").lower() != "real" or not os.getenv("CAPITALPAY_KEY"),
    reason="Set CAPITALPAY_MODE=real and CapitalPay credentials in .env",
)


def test_live_create_signed_invoice_service_fee():
    from services.capitalpay import clear_token_cache, create_signed_invoice
    from services.gn83 import calculate_invoice, lookup_fee

    clear_token_cache()
    std = lookup_fee("Import", "Sea", "MOTOR_VEHICLE")
    calc = calculate_invoice(std, "FULL_SETTLEMENT")
    result = create_signed_invoice(
        client_invoice_ref="INV-ZCAMS-LIVE-SVC-001",
        amount=calc["total"],
        invoice_type="FULL_SETTLEMENT",
        calc=calc,
        customer_name="David Kimani",
        email="cwakhusama@gmail.com",
        msisdn="0713265048",
        id_number="198293216-63766-9",
        bl_number="MSC0620430218",
        z_sad_number="Z-SAD-LIVE-TEST",
    )
    assert result["mode"] == "real"
    assert result["invoice_number"].startswith("CPAY")
    assert not result["invoice_number"].startswith("CPAYMOCK")
    assert result["amount_expected"] == calc["total"]
    print(f"CapitalPay invoice_number: {result['invoice_number']}")
