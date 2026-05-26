"""Quick live CapitalPay invoice create test."""
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
base = os.getenv("CAPITALPAY_BASE_URL", "https://app.capitalpay.co.tz/api").rstrip("/")
r = requests.post(
    f"{base}/oauth/generate/token",
    json={"key": os.getenv("CAPITALPAY_KEY"), "secret": os.getenv("CAPITALPAY_SECRET")},
    timeout=30,
)
token = r.json()["token"]
for amt in ("212.40", "212.50", "213.00", "184.08", "185.00"):
    body = {
        "account_id": "48",
        "amount_expected": amt,
        "amount_settled_offline": 0,
        "callback_url": "https://dummy-merchant.example.com/payment/callback",
        "client_invoice_ref": f"INV-SINGLE-{amt.replace('.', '')}",
        "currency": "USD",
        "email": "cwakhusama@gmail.com",
        "format": "json",
        "id_number": "198293216-63766-9",
        "items": [
            {
                "account_id": 48,
                "desc": "ZCAMS GN 83 Service Fee",
                "item_ref": "ITEM-001",
                "price": amt,
                "quantity": "1",
                "require_settlement": "true",
            }
        ],
        "msisdn": "+255713265048",
        "name": "David Kimani",
        "notification_url": "https://dummy-merchant.example.com/payment/notify",
        "payment_gateway_id": 1,
        "send_stk": False,
    }
    r2 = requests.post(
        f"{base}/invoice/create",
        json=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=45,
    )
    inv = r2.json().get("invoice") or {}
    print(amt, r2.status_code, inv.get("invoice_number"), inv.get("amount_expected"))
