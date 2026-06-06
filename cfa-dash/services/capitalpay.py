from __future__ import annotations

import base64
import hashlib
import hmac
import os
import random
import re
import string
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from services.messaging import normalize_zambia_phone


class CapitalPayError(RuntimeError):
    pass


_TOKEN_CACHE: dict[str, Any] = {}


def _mock_enabled() -> bool:
    """Return True only for explicit test/demo runs.

    Production must always sign through the real CapitalPay API. We never
    silently fall back to mock just because credentials are missing — that
    would let a misconfigured deploy emit dummy CPAYMOCK… invoices to real
    importers. Missing creds raise CapitalPayError downstream instead.
    """
    mode = os.getenv("CAPITALPAY_MODE", "real").strip().lower()
    allow_mock = os.getenv("ZCAMS_ALLOW_MOCK_CAPITALPAY", "").strip().lower() in {"1", "true", "yes"}
    running_tests = bool(os.getenv("PYTEST_CURRENT_TEST"))
    return mode == "mock" and (allow_mock or running_tests)


def _base_url() -> str:
    return os.getenv("CAPITALPAY_BASE_URL", "https://app.capitalpay.co.tz/api").rstrip("/")


def _checkout_url() -> str:
    return os.getenv("CAPITALPAY_CHECKOUT_URL", "https://app.capitalpay.co.tz/PaymentAPI/invoice/checkout").strip()


def _public_base_url() -> str:
    return os.getenv("PUBLIC_APP_URL", "http://127.0.0.1:8050").rstrip("/")


def _config() -> dict[str, str]:
    base = _public_base_url()
    return {
        "key": os.getenv("CAPITALPAY_KEY", os.getenv("CAPITALPAY_API_KEY", "")),
        "secret": os.getenv("CAPITALPAY_SECRET", os.getenv("CAPITALPAY_WEBHOOK_SECRET", "")),
        "account_id": os.getenv("CAPITALPAY_ACCOUNT_ID", os.getenv("CAPITALPAY_MERCHANT_ID", "48")),
        "payment_gateway_id": os.getenv("CAPITALPAY_PAYMENT_GATEWAY_ID", "1"),
        "callback_url": (os.getenv("CAPITALPAY_CALLBACK_URL") or "").strip()
        or f"{base}/api/capitalpay/callback",
        "notification_url": (os.getenv("CAPITALPAY_NOTIFICATION_URL") or "").strip()
        or f"{base}/api/capitalpay/notify",
    }


def _mock_capitalpay_number() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase, k=6))
    return f"CPAYMOCK{suffix}"


def _format_msisdn(phone: str | None) -> str:
    if not phone:
        return ""
    raw = str(phone).strip()
    if raw.startswith("+"):
        return raw
    digits = normalize_zambia_phone(phone)
    return f"+{digits}" if digits else ""


def normalize_checkout_html(html: str) -> str:
    public_host = os.getenv("CAPITALPAY_PUBLIC_HOST", "https://app.capitalpay.co.tz").rstrip("/")
    private_hosts = (
        "https://192.168.92.110",
        "http://192.168.92.110",
    )
    for private_host in private_hosts:
        html = html.replace(private_host, public_host)
    return html


def extract_checkout_payment_ref(html: str) -> str | None:
    """Extract the payment reference displayed by CapitalPay checkout."""
    if not html:
        return None
    payment_ref_match = re.search(r"PAYMENT\s*REF.*?(CPAY[A-Z0-9]+)", html, flags=re.IGNORECASE | re.DOTALL)
    if payment_ref_match:
        return payment_ref_match.group(1).upper()
    any_ref_match = re.search(r"\b(CPAY[A-Z0-9]{6,})\b", html, flags=re.IGNORECASE)
    return any_ref_match.group(1).upper() if any_ref_match else None


def capitalpay_payable_amount(calc_total: float) -> float:
    """CapitalPay checkout amount equals the GN 83 invoice total."""
    return float(calc_total)


def _item_simple(
    *,
    account_id: int,
    desc: str,
    item_ref: str,
    price: float,
) -> dict[str, Any]:
    """Line item format matching CapitalPay TZ API (no nested settlements array)."""
    return {
        "account_id": account_id,
        "desc": desc,
        "item_ref": item_ref,
        "price": f"{price:.2f}",
        "quantity": "1",
        "require_settlement": "true",
    }


def _build_items(
    invoice_type: str,
    calc: dict[str, float],
    bl_number: str,
    z_sad_number: str,
    payable: float,
) -> list[dict[str, Any]]:
    account_id = int(_config()["account_id"])
    ref_suffix = (bl_number or "BL")[-8:].upper().replace(" ", "X")
    desc = f"ZCAMS GN 83 Full Settlement | BL {bl_number} | Z-SAD {z_sad_number}"
    item_ref = f"ITEM-FULL-{ref_suffix}"
    return [_item_simple(account_id=account_id, desc=desc, item_ref=item_ref, price=payable)]


def _build_create_payload(
    *,
    client_invoice_ref: str,
    invoice_type: str,
    calc: dict[str, float],
    customer_name: str,
    email: str | None,
    msisdn: str | None,
    id_number: str | None,
    bl_number: str,
    z_sad_number: str,
) -> dict[str, Any]:
    cfg = _config()
    payable = capitalpay_payable_amount(calc["total"])
    items = _build_items(invoice_type, calc, bl_number, z_sad_number, payable)
    return {
        "account_id": str(cfg["account_id"]),
        "amount_expected": f"{payable:.2f}",
        "amount_settled_offline": 0,
        "callback_url": cfg["callback_url"],
        "client_invoice_ref": client_invoice_ref,
        "currency": "USD",
        "email": email or "",
        "format": "json",
        "id_number": id_number or z_sad_number or client_invoice_ref,
        "items": items,
        "msisdn": _format_msisdn(msisdn),
        "name": customer_name or "ZCAMS Importer",
        "notification_url": cfg["notification_url"],
        "payment_gateway_id": int(cfg["payment_gateway_id"]),
        "send_stk": False,
    }


def _checkout_url_for(invoice_number: str) -> str:
    template = os.getenv("CAPITALPAY_PAY_URL_TEMPLATE", "https://app.capitalpay.co.tz/pay/{invoice_number}")
    return template.format(invoice_number=invoice_number)


def clear_token_cache() -> None:
    _TOKEN_CACHE.clear()


def _auth_headers(token: str) -> dict[str, str]:
    style = os.getenv("CAPITALPAY_AUTH_STYLE", "bearer").lower()
    if style == "token":
        return {"token": token, "Content-Type": "application/json"}
    if style == "raw":
        return {"Authorization": token, "Content-Type": "application/json"}
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _get_token() -> str:
    cfg = _config()
    if not cfg["key"] or not cfg["secret"]:
        raise CapitalPayError("CapitalPay key and secret are required when CAPITALPAY_MODE=real.")

    cached = _TOKEN_CACHE.get("token")
    expires_at = _TOKEN_CACHE.get("expires_at")
    if cached and expires_at and datetime.now(timezone.utc) < expires_at:
        return cached

    url = f"{_base_url()}/oauth/generate/token"
    response = requests.post(url, json={"key": cfg["key"], "secret": cfg["secret"]}, timeout=30)
    try:
        payload = response.json()
    except ValueError as exc:
        raise CapitalPayError(f"CapitalPay auth returned non-JSON (HTTP {response.status_code}).") from exc

    if response.status_code >= 400 or not payload.get("token"):
        raise CapitalPayError(f"CapitalPay auth failed (HTTP {response.status_code}): {payload}")

    expiry_seconds = int(payload.get("expiry") or 3500)
    _TOKEN_CACHE["token"] = payload["token"]
    _TOKEN_CACHE["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=max(expiry_seconds - 60, 60))
    return payload["token"]


def _signed_result(capitalpay_number: str, body: dict[str, Any], payload: dict[str, Any], mode: str) -> dict[str, Any]:
    invoice = payload.get("invoice") or {}
    amount_expected = float(invoice.get("amount_expected") or body["amount_expected"])
    return {
        "urn": capitalpay_number,
        "capitalpay_number": capitalpay_number,
        "invoice_number": capitalpay_number,
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "checkout_url": _checkout_url_for(capitalpay_number),
        "reference": capitalpay_number,
        "mode": mode,
        "raw": payload,
        "service": invoice.get("service"),
        "amount_expected": amount_expected,
        "client_invoice_ref": body.get("client_invoice_ref"),
    }


def create_signed_invoice(
    *,
    client_invoice_ref: str,
    amount: float,
    invoice_type: str,
    calc: dict[str, float],
    customer_name: str,
    email: str | None = None,
    msisdn: str | None = None,
    id_number: str | None = None,
    bl_number: str = "",
    z_sad_number: str = "",
    settlement_account: str | None = None,
) -> dict[str, Any]:
    del amount, settlement_account  # payable derived from calc["total"] (GN 83 invoice total)
    if _mock_enabled():
        capitalpay_number = _mock_capitalpay_number()
        body = _build_create_payload(
            client_invoice_ref=client_invoice_ref,
            invoice_type=invoice_type,
            calc=calc,
            customer_name=customer_name,
            email=email,
            msisdn=msisdn,
            id_number=id_number,
            bl_number=bl_number,
            z_sad_number=z_sad_number,
        )
        return {
            **_signed_result(capitalpay_number, body, {"invoice": {"amount_expected": body["amount_expected"]}}, "mock"),
            "checkout_url": f"{_public_base_url()}/checkout?invoice={client_invoice_ref}",
        }

    token = _get_token()
    body = _build_create_payload(
        client_invoice_ref=client_invoice_ref,
        invoice_type=invoice_type,
        calc=calc,
        customer_name=customer_name,
        email=email,
        msisdn=msisdn,
        id_number=id_number,
        bl_number=bl_number,
        z_sad_number=z_sad_number,
    )
    url = f"{_base_url()}/invoice/create"
    response = requests.post(url, json=body, headers=_auth_headers(token), timeout=45)
    try:
        payload = response.json()
    except ValueError as exc:
        raise CapitalPayError(f"CapitalPay invoice/create returned non-JSON (HTTP {response.status_code}).") from exc

    if response.status_code >= 400 or payload.get("status") not in {200, "200"}:
        raise CapitalPayError(f"CapitalPay invoice/create failed (HTTP {response.status_code}): {payload}")

    invoice = payload.get("invoice") or {}
    capitalpay_number = invoice.get("invoice_number")
    if not capitalpay_number:
        raise CapitalPayError(f"CapitalPay response missing invoice.invoice_number: {payload}")

    return _signed_result(capitalpay_number, body, payload, "real")


def sign_invoice(invoice_number: str, amount: float, **kwargs: Any) -> dict:
    """Backward-compatible wrapper; prefer create_signed_invoice with full KYC context."""
    return create_signed_invoice(
        client_invoice_ref=invoice_number,
        amount=amount,
        invoice_type=kwargs.get("invoice_type", "FULL_SETTLEMENT"),
        calc=kwargs.get("calc") or {"std_min_fee": amount, "admin_fee": 0.0, "vat": 0.0, "total": amount},
        customer_name=kwargs.get("customer_name", "ZCAMS Importer"),
        email=kwargs.get("email"),
        msisdn=kwargs.get("msisdn"),
        id_number=kwargs.get("id_number"),
        bl_number=kwargs.get("bl_number", ""),
        z_sad_number=kwargs.get("z_sad_number", ""),
    )


def create_checkout_link(invoice_id: str, z_sad_number: str, amount: float, capitalpay_invoice_number: str | None = None) -> dict:
    del z_sad_number, amount
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    if _mock_enabled():
        return {
            "checkout_url": f"{_public_base_url()}/checkout?invoice={invoice_id}",
            "reference": capitalpay_invoice_number or f"CP-MOCK-{invoice_id[:8].upper()}",
            "expires_at": expires.isoformat(),
            "mode": "mock",
        }
    number = capitalpay_invoice_number or ""
    return {
        "checkout_url": _checkout_url_for(number) if number else "",
        "reference": number,
        "expires_at": expires.isoformat(),
        "mode": "real",
    }


def compute_checkout_secure_hash(
    *,
    api_client_id: str,
    amount: str,
    service_id: str,
    client_id_number: str,
    currency: str,
    bill_ref_number: str,
    bill_desc: str,
    client_name: str,
) -> str:
    cfg = _config()
    data_string = (
        api_client_id
        + amount
        + service_id
        + client_id_number
        + currency
        + bill_ref_number
        + bill_desc
        + client_name
        + cfg["secret"]
    )
    raw_hash = hmac.new(cfg["key"].encode(), data_string.encode(), hashlib.sha256).digest()
    return base64.b64encode(raw_hash).decode()


def build_checkout_params(
    *,
    client_name: str,
    client_msisdn: str | None,
    client_email: str | None,
    client_id_number: str,
    amount: float,
    currency: str,
    bill_ref_number: str,
    bill_desc: str,
) -> dict[str, str]:
    cfg = _config()
    account_id = str(cfg["account_id"])
    amount_str = f"{float(amount):.2f}"
    params = {
        "apiClientID": account_id,
        "secureHash": compute_checkout_secure_hash(
            api_client_id=account_id,
            amount=amount_str,
            service_id=account_id,
            client_id_number=client_id_number,
            currency=currency,
            bill_ref_number=bill_ref_number,
            bill_desc=bill_desc,
            client_name=client_name,
        ),
        "billDesc": bill_desc,
        "billRefNumber": bill_ref_number,
        "currency": currency,
        "serviceID": account_id,
        "clientMSISDN": _format_msisdn(client_msisdn),
        "clientName": client_name,
        "clientIDNumber": client_id_number,
        "clientEmail": client_email or "",
        "notificationURL": cfg["notification_url"],
        "amountExpected": amount_str,
    }
    if cfg["callback_url"]:
        params["callBackURLOnSuccess"] = cfg["callback_url"]
    return params


def fetch_checkout_page(params: dict[str, str]) -> str:
    response = requests.post(_checkout_url(), data=params, timeout=45)
    if not response.ok:
        raise CapitalPayError(f"CapitalPay checkout failed (HTTP {response.status_code}): {response.text[:300]}")
    return normalize_checkout_html(response.text)
