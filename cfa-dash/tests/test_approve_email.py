import os
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from services.db import connect
from services.repository import approve_company, bootstrap, create_onboarding


def _cleanup_company(company_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM notifications WHERE company_id = ?", (company_id,))
        conn.execute("DELETE FROM certificates WHERE company_id = ?", (company_id,))
        conn.execute("DELETE FROM users WHERE company_id = ?", (company_id,))
        conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))
        conn.commit()


@patch("services.repository.send_new_user_registration_email")
def test_approve_company_sends_credentials(mock_send):
    bootstrap()
    mock_send.return_value = {"sent": True, "mode": "bird"}
    created = create_onboarding(
        {
            "first_name": "Test",
            "last_name": "CFA",
            "email": "test-cfa-approve@zcams.test",
            "username": "testcfaapprove",
            "password": "OriginalPass1!",
            "company_name": "Test CFA Email Co",
            "pacra_number": "PACRA-1",
            "tpin": "TPIN-1",
            "zra_licence": "ZRA-1",
            "address_line1": "Line 1",
            "city": "Lusaka",
            "province": "Lusaka",
            "bank_name": "ZANACO",
            "account_number": "123",
            "account_holder": "Test CFA Email Co",
        }
    )
    company_id = created["company_id"]
    try:
        result = approve_company(company_id)
        assert result["credentials_sent"] is True
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == "test-cfa-approve@zcams.test"
        assert "approved" in args[1].lower()
        assert "ZCAMS-" in args[2]
        assert kwargs.get("html")
    finally:
        _cleanup_company(company_id)
