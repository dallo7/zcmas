import os
from unittest.mock import MagicMock, patch

import pytest

from services.capitalpay import (
    CapitalPayError,
    _build_create_payload,
    capitalpay_payable_amount,
    clear_token_cache,
    create_signed_invoice,
    fetch_checkout_page,
)


@pytest.fixture(autouse=True)
def _reset_capitalpay_token_cache():
    clear_token_cache()
    yield
    clear_token_cache()


def test_capitalpay_payable_matches_gn83_total():
    assert capitalpay_payable_amount(35.0) == 35.0
    assert capitalpay_payable_amount(209.0) == 209.0
    assert capitalpay_payable_amount(181.0) == 181.0


def test_build_create_payload_single_item_format():
    calc = {"std_min_fee": 150.0, "admin_fee": 30.0, "vat": 4.8, "total": 35.0}
    payload = _build_create_payload(
        client_invoice_ref="INV-TEST-1",
        invoice_type="SERVICE_FEE_ONLY",
        calc=calc,
        customer_name="ETS ARAKA",
        email="importer@example.com",
        msisdn="0971234567",
        id_number="1000123456",
        bl_number="MSC0620430218",
        z_sad_number="Z-SAD-TEST",
    )
    assert payload["amount_expected"] == "35.00"
    assert len(payload["items"]) == 1
    assert payload["items"][0]["price"] == "35.00"
    assert "settlements" not in payload["items"][0]
    assert payload["msisdn"] == "+260971234567"


@patch.dict(os.environ, {"CAPITALPAY_MODE": "real"}, clear=False)
@patch("services.capitalpay.requests.post")
def test_create_signed_invoice_uses_api_invoice_number(mock_post):
    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = {"token": "test-token", "expiry": 3600}

    invoice_response = MagicMock()
    invoice_response.status_code = 200
    invoice_response.json.return_value = {
        "status": 200,
        "message": "success",
        "invoice": {
            "service": "ZCAMS GN 83",
            "invoice_number": "CPAYQKWKMQ",
            "customer_name": "ETS ARAKA",
            "currency": "USD",
            "amount_expected": "35.00",
        },
    }
    mock_post.side_effect = [token_response, invoice_response]

    with patch.dict(
        os.environ,
        {
            "CAPITALPAY_KEY": "test-key",
            "CAPITALPAY_SECRET": "test-secret",
            "CAPITALPAY_ACCOUNT_ID": "48",
        },
        clear=False,
    ):
        result = create_signed_invoice(
            client_invoice_ref="INV-20260520-TEST",
            amount=35.0,
            invoice_type="SERVICE_FEE_ONLY",
            calc={"std_min_fee": 150.0, "admin_fee": 30.0, "vat": 4.8, "total": 35.0},
            customer_name="ETS ARAKA",
            email="importer@example.com",
            msisdn="0971234567",
            bl_number="MSC0620430218",
            z_sad_number="Z-SAD-TEST",
        )

    assert result["invoice_number"] == "CPAYQKWKMQ"
    assert result["urn"] == "CPAYQKWKMQ"
    assert result["mode"] == "real"
    assert result["checkout_url"].endswith("/pay/CPAYQKWKMQ")
    create_call = mock_post.call_args_list[1]
    assert create_call.kwargs["json"]["amount_expected"] == "35.00"
    assert len(create_call.kwargs["json"]["items"]) == 1


@patch.dict(os.environ, {"CAPITALPAY_MODE": "mock", "ZCAMS_ALLOW_MOCK_CAPITALPAY": "true"}, clear=False)
def test_mock_mode_uses_cpaysmock_prefix():
    result = create_signed_invoice(
        client_invoice_ref="INV-MOCK",
        amount=35.0,
        invoice_type="SERVICE_FEE_ONLY",
        calc={"std_min_fee": 150.0, "admin_fee": 30.0, "vat": 4.8, "total": 35.0},
        customer_name="Test",
    )
    assert result["invoice_number"].startswith("CPAYMOCK")
    assert result["mode"] == "mock"


@patch.dict(
    os.environ,
    {
        "CAPITALPAY_MODE": "mock",
        "ZCAMS_ALLOW_MOCK_CAPITALPAY": "true",
        "CAPITALPAY_CHECKOUT_URL": "https://app.capitalpay.co.tz/PaymentAPI/invoice/checkout",
    },
    clear=False,
)
@patch("services.capitalpay.requests.post")
def test_checkout_page_always_uses_capitalpay_endpoint(mock_post):
    response = MagicMock()
    response.ok = True
    response.text = "<html>CapitalPay checkout</html>"
    mock_post.return_value = response

    html = fetch_checkout_page({"billRefNumber": "CPAYREAL", "amountExpected": "35.00"})

    assert html == "<html>CapitalPay checkout</html>"
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "https://app.capitalpay.co.tz/PaymentAPI/invoice/checkout"


@patch.dict(os.environ, {"CAPITALPAY_MODE": "real", "CAPITALPAY_KEY": "", "CAPITALPAY_SECRET": ""}, clear=False)
def test_create_signed_invoice_requires_credentials():
    with pytest.raises(CapitalPayError):
        create_signed_invoice(
            client_invoice_ref="INV-TEST",
            amount=10.0,
            invoice_type="SERVICE_FEE_ONLY",
            calc={"std_min_fee": 10.0, "admin_fee": 2.5, "vat": 0.0, "total": 2.5},
            customer_name="Test",
        )
