import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from services.bird_email import send_bird_email
from services.messaging import send_email


@patch.dict(
    os.environ,
    {
        "BIRD_EMAIL_MODE": "api",
        "BIRD_EMAIL_ACCESS_KEY": "test-key",
        "BIRD_EMAIL_API_URL": "https://email.test/transmissions",
    },
    clear=False,
)
@patch("services.bird_email.requests.post")
def test_send_bird_email_success(mock_post):
    mock_post.return_value = MagicMock(status_code=202, content=b'{"id":"tx-1"}', json=lambda: {"id": "tx-1"})
    result = send_bird_email(
        "client@example.com",
        "Test",
        "Hello",
        recipient_name="Client",
    )
    assert result["sent"] is True
    assert result["mode"] == "bird"
    mock_post.assert_called_once()


@patch.dict(os.environ, {"BIRD_EMAIL_MODE": "mock"}, clear=False)
def test_send_email_mock_without_bird():
    result = send_email("nobody@example.com", "Subject", "Body")
    assert result["sent"] is False
    assert result["mode"] == "mock"


@patch.dict(
    os.environ,
    {
        "BIRD_EMAIL_MODE": "api",
        "BIRD_EMAIL_ACCESS_KEY": "test-key",
    },
    clear=False,
)
@patch("services.messaging.send_bird_email")
def test_send_email_routes_to_bird(mock_bird):
    mock_bird.return_value = {"sent": True, "mode": "bird"}
    result = send_email("cwakhusama@gmail.com", "Invoice", "Please pay", recipient_name="Client")
    assert result["sent"] is True
    mock_bird.assert_called_once()
