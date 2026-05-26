from __future__ import annotations

import base64
import binascii
import threading
from pathlib import Path
from typing import Any

from services import ocr, repository
from services.db import UPLOAD_DIR
from services.gn83 import gn83_quote_for_reviewed


FIVE_VALUE_KEYS = (
    "bl_number",
    "consignee_tin",
    "gross_weight",
    "no_containers",
    "invoice_type",
)

_SHARE_LOCK = threading.Lock()
_SHARE_CACHE: dict[str, dict[str, Any]] = {}


def save_agentic_upload(contents: str, filename: str | None) -> Path:
    if not contents or "," not in contents:
        raise ValueError("Upload a valid BL file before starting Agentic Mode.")
    safe_name = repository.safe_filename(filename or "agentic-bl.pdf")
    target_dir = UPLOAD_DIR / "agentic-bls"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name
    try:
        target.write_bytes(base64.b64decode(contents.split(",", 1)[1]))
    except (binascii.Error, ValueError) as exc:
        raise ValueError("The uploaded BL could not be decoded.") from exc
    return target


def extract_agentic_bl(file_path: str) -> dict[str, Any]:
    extracted = ocr.extract_bl_fields(file_path)
    extracted["file_path"] = file_path
    return extracted


def five_value_snapshot(
    extracted: dict | None,
    *,
    bl_number: str | None,
    consignee_tin: str | None,
    gross_weight: float | str | None,
    no_containers: int | str | None,
    gn83_category: str | None,
    invoice_type: str | None,
) -> dict[str, Any]:
    data = dict(extracted or {})
    data.update(
        {
            "bl_number": str(bl_number or "").strip(),
            "consignee_tin": str(consignee_tin or "").strip(),
            "gross_weight": _float(gross_weight),
            "no_containers": _int(no_containers),
            "gn83_category": gn83_category or data.get("gn83_category") or "LOOSE_LCL",
            "invoice_type": invoice_type or "SERVICE_FEE_ONLY",
        }
    )
    return data


def validate_five_values(data: dict, *, confirmed: bool, channels: list[str] | None, email: str | None, phone: str | None) -> None:
    missing = []
    if not data.get("bl_number"):
        missing.append("BL Number")
    if not data.get("consignee_tin"):
        missing.append("Consignee/Consigner TIN")
    if data.get("gross_weight") in {None, ""}:
        missing.append("Gross Weight")
    if data.get("no_containers") is None:
        missing.append("No. of containers / loose cargo / LCL")
    if data.get("invoice_type") not in {"SERVICE_FEE_ONLY", "FULL_SETTLEMENT"}:
        missing.append("Service Fee Only / Full Settlement")
    selected = {str(channel).upper() for channel in (channels or [])}
    if "EMAIL" in selected and not str(email or "").strip():
        missing.append("Client email")
    if "WHATSAPP" in selected and not str(phone or "").strip():
        missing.append("Client phone / WhatsApp")
    if not selected:
        missing.append("At least one share channel")
    if missing:
        raise ValueError("Re-check required: " + ", ".join(missing) + ".")
    if not confirmed:
        raise ValueError("Confirm the five-value re-check before Agentic Mode generates or sends anything.")


def build_bl_payload(data: dict, *, file_name: str | None = None) -> dict[str, Any]:
    return {
        **data,
        "doc_type": data.get("doc_type") or "Bill of Lading",
        "route_type": data.get("route_type") or "Import",
        "transport_mode": data.get("transport_mode") or "Sea",
        "zra_regime": data.get("zra_regime") or "IM4 Home Use",
        "consignee_name": data.get("consignee_name") or "Importer",
        "origin": data.get("origin") or "",
        "destination": data.get("destination") or "",
        "cargo_description": data.get("cargo_description") or "General cargo",
        "file_name": file_name or data.get("file_name") or "agentic-bl.pdf",
        "file_path": data.get("file_path"),
    }


def create_agentic_bl(data: dict, *, company_id: str = repository.DEMO_COMPANY_ID) -> dict:
    return repository.create_bl(
        build_bl_payload(data, file_name=data.get("file_name")),
        auto_review=False,
        use_ocr_defaults=False,
        company_id=company_id,
    )


def issue_agentic_zsad(bl_id: str) -> dict:
    return repository.review_bl(bl_id)


def generate_and_share_agentic_invoice(
    reviewed_id: str,
    *,
    invoice_type: str,
    email: str | None,
    phone: str | None,
    channels: list[str] | None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    cache_key = (idempotency_key or "").strip()
    if cache_key:
        with _SHARE_LOCK:
            cached = _SHARE_CACHE.get(cache_key)
            if cached:
                return cached
            result = _generate_and_share_invoice(reviewed_id, invoice_type=invoice_type, email=email, phone=phone, channels=channels)
            _SHARE_CACHE[cache_key] = result
            return result

    return _generate_and_share_invoice(reviewed_id, invoice_type=invoice_type, email=email, phone=phone, channels=channels)


def generate_agentic_invoice_for_review(
    reviewed_id: str,
    *,
    invoice_type: str,
    email: str | None,
    phone: str | None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    cache_key = f"{(idempotency_key or '').strip()}:invoice"
    if cache_key != ":invoice":
        with _SHARE_LOCK:
            cached = _SHARE_CACHE.get(cache_key)
            if cached:
                return cached["invoice"]
            invoice = repository.generate_invoice(
                reviewed_id,
                invoice_type,
                contact_phone=str(phone or "").strip() or None,
                contact_email=str(email or "").strip() or None,
            )
            _SHARE_CACHE[cache_key] = {"invoice": invoice}
            return invoice

    return repository.generate_invoice(
        reviewed_id,
        invoice_type,
        contact_phone=str(phone or "").strip() or None,
        contact_email=str(email or "").strip() or None,
    )


def share_agentic_invoice_after_review(
    invoice_id: str,
    *,
    email: str | None,
    phone: str | None,
    channels: list[str] | None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    cache_key = f"{(idempotency_key or '').strip()}:share"
    if cache_key != ":share":
        with _SHARE_LOCK:
            cached = _SHARE_CACHE.get(cache_key)
            if cached:
                return cached
            result = repository.share_invoice_with_importer(
                invoice_id,
                channels=channels or ["WHATSAPP"],
                contact_email=str(email or "").strip() or None,
            )
            _SHARE_CACHE[cache_key] = result
            return result

    return repository.share_invoice_with_importer(
        invoice_id,
        channels=channels or ["WHATSAPP"],
        contact_email=str(email or "").strip() or None,
    )


def _generate_and_share_invoice(
    reviewed_id: str,
    *,
    invoice_type: str,
    email: str | None,
    phone: str | None,
    channels: list[str] | None,
) -> dict[str, Any]:
    invoice = repository.generate_invoice(
        reviewed_id,
        invoice_type,
        contact_phone=str(phone or "").strip() or None,
        contact_email=str(email or "").strip() or None,
    )
    share_results = repository.share_invoice_with_importer(
        invoice["id"],
        channels=channels or ["WHATSAPP"],
        contact_email=str(email or "").strip() or None,
    )
    return {"invoice": invoice, "share_results": share_results}


def agentic_guidance(extracted: dict | None) -> str:
    if not extracted:
        return "Upload a BL to begin. I will extract draft values and pause for your five-value re-check."
    category = extracted.get("gn83_category") or "GN 83 category not detected"
    containers = extracted.get("no_containers")
    if category == "LOOSE_LCL":
        risk = "This looks like loose or LCL cargo, so GN 83 should not multiply the minimum fee by container count."
    elif containers and int(containers or 0) > 1:
        risk = f"This looks like a multi-container BL. Confirm the container count before invoicing because GN 83 may multiply by {containers}."
    else:
        risk = "This looks like a single shipment. Confirm the invoice type and client contacts before sending."
    return f"Draft BL {extracted.get('bl_number') or '-'} extracted. {risk}"


def summarize_result(invoice: dict, reviewed: dict, share_results: dict) -> dict[str, Any]:
    quote = gn83_quote_for_reviewed(reviewed)
    return {
        "bl_number": invoice.get("bl_number"),
        "z_sad_number": invoice.get("z_sad_number"),
        "invoice_number": invoice.get("invoice_number"),
        "invoice_type": invoice.get("invoice_type"),
        "total": invoice.get("total"),
        "std_min_fee": invoice.get("std_min_fee"),
        "gn83_category": quote.get("category"),
        "units": quote.get("units"),
        "pdf_url": repository.invoice_download_url(invoice["id"]),
        "whatsapp_url": (share_results.get("whatsapp") or {}).get("url"),
        "email": share_results.get("email"),
    }


def _float(value: float | str | None) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _int(value: int | str | None) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)
