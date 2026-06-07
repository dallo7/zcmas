from __future__ import annotations

import base64
import io
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path


DEMO_EXTRACTION = {
    "bl_number": "BL-ZM-KBCX",
    "doc_type": "Bill of Lading",
    "route_type": "Import",
    "transport_mode": "Sea",
    "zra_regime": "IM4 Home Use",
    "shipper_name": "Demo Shipper Ltd",
    "shipper_address": "Port of Dar es Salaam",
    "shipper_country": "Tanzania",
    "carrier_name": "Demo Lines",
    "vessel_vehicle_no": "MV ZAMBIA DEMO",
    "origin": "Dar es Salaam",
    "destination": "Lusaka",
    "consignee_tin": "1000123456",
    "consignee_name": "Copper Belt Imports Ltd",
    "gross_weight": 18.5,
    "no_containers": 1,
    "cargo_description": "Motor vehicles and spare parts",
    "hs_code": "8703.23",
    "quantity": 1,
    "unit": "Unit",
    "gn83_category": "MOTOR_VEHICLE",
}

MISSING_STRING = "Put Value"

EXTRACTION_SCHEMA_DEFAULTS = {
    "bl_type": MISSING_STRING,
    "currency": MISSING_STRING,
    "bl_number": MISSING_STRING,
    "agentLicense": MISSING_STRING,
    "agent_license": MISSING_STRING,
    "company_name": MISSING_STRING,
    "consignee_tin": MISSING_STRING,
    "consignor_tin": MISSING_STRING,
    "declarant_number": MISSING_STRING,
    "consignment_value": None,
    "document_type": MISSING_STRING,
    "doc_type": MISSING_STRING,
    "transport_mode": MISSING_STRING,
    "zra_regime": MISSING_STRING,
    "consignee": MISSING_STRING,
    "consignee_name": MISSING_STRING,
    "origin": MISSING_STRING,
    "destination": MISSING_STRING,
    "no_of_containers": None,
    "no_containers": None,
    "gross_weight_mt": None,
    "gross_weight": None,
    "cargo_description": MISSING_STRING,
    "gn83_category": MISSING_STRING,
    "gn83_unit": MISSING_STRING,
    "gn83_fee_usd": None,
}

STRUCTURED_BL_EXTRACTION_PROMPT = """
You are a customs document extraction specialist. Your task is to extract structured data from shipping documents — Bills of Lading (BOL) and Air Waybills (AWB) — and return a JSON object matching the schema below.

Return ONLY valid JSON — no markdown, no explanation:
{
  "bl_type": "",
  "currency": "",
  "bl_number": "",
  "agentLicense": "",
  "company_name": "",
  "consignee_tin": "",
  "consignor_tin": "",
  "declarant_number": "",
  "consignment_value": null,
  "document_type": "",
  "transport_mode": "",
  "zra_regime": "",
  "consignee": "",
  "origin": "",
  "destination": "",
  "no_of_containers": null,
  "gross_weight_mt": null,
  "cargo_description": "",
  "gn83_category": "",
  "gn83_unit": "",
  "gn83_fee_usd": null
}

Extraction rules:
- bl_type: IMPORT AWB/BOL -> IM4. EXPORT AWB/BOL -> EX1. Use document type and pre-carriage/transport direction. Default imports to IM4 and exports to EX1.
- currency: use stated currency from freight, invoice value, LC, symbols, or ISO code. If absent return "Put Value".
- bl_number: use Bill of Lading Number, Air Waybill Number, AWB Number, or BOL Number exactly as printed. If absent return "Put Value".
- agentLicense and declarant_number: use ZRA REG. NO, Agent License, ZRA Agent Registration, Customs Agent No, footer/signatory registration. If absent return "Put Value".
- company_name: shipper for export, consignee for import. Use first legal-name line. If absent return "Put Value".
- consignee_tin and consignor_tin: use TIN, Tax Identification Number, ZRA TPN, VAT No, or associated tax numbers. If absent return "Put Value".
- consignment_value: numeric invoice/customs/CIF/FOB/declared/consignment/freight value, without currency symbol. If absent return null.
- document_type: normalize to "Bill of Lading" or "Air Waybill". If absent return "Put Value".
- transport_mode: normalize to "Sea", "Air", "Road", or "Rail". If absent return "Put Value".
- zra_regime: IM4 -> "IM4 Home Use", EX1 -> "EX1 Export", IM7 -> "IM7 Warehousing", IM8 -> "IM8 Temporary Import". If absent return "Put Value".
- consignee: full consignee company name. If absent return "Put Value".
- origin: Port of Loading, Place of Receipt, Origin, or shipper country. If absent return "Put Value".
- destination: Port of Discharge, Place of Delivery, or Final Destination. If absent return "Put Value".
- no_of_containers: numeric total containers/units; air/loose cargo returns 0. If absent return null.
- gross_weight_mt: total gross weight converted to metric tonnes. KG / 1000. If absent return null.
- cargo_description: concise goods summary. If absent return "Put Value".

GN 83 matching rules:
- bl_type starting IM uses Import, EX uses Export, T/transit uses Transit.
- Sea/Inland Waterways, Road/Rail, and Air sections must be matched from transport_mode.
- Sea/Road containers: 20-foot and 40-foot containers match by container size text or counts.
- Bulk dry/liquid uses MT and fee = gross_weight_mt * 0.6 rounded to 2 decimals.
- Vehicle keywords or HS 87xx -> Motor Vehicle. Heavy machine keywords -> Heavy Machines & Equipment. Live animal keywords -> Live Animal.
- Loose/LCL/no containers -> Loose Cargo/Less than Container Load.
- Air parcel/courier -> Parcel / Couriers. Air live animal -> Live Animal. Export precious minerals/metals -> Precious Metal/Minerals. Other air cargo -> General Cargo.
- Populate gn83_category with the tariff description, gn83_unit with the unit, and gn83_fee_usd with a number.

Missing value rule:
- Use "Put Value" for missing strings.
- Use null for missing numeric fields.
- Do not invent, assume, or carry over values from other documents.
"""


def extract_bl_fields(file_path: str | None = None) -> dict:
    if not file_path:
        return {**DEMO_EXTRACTION, "ocr_provider": "mock", "ocr_mode": "demo"}

    path = Path(file_path)
    provider = os.getenv("OCR_PROVIDER", "openai").lower()
    try:
        if path.suffix.lower() == ".pdf":
            text, mode, ocr_provider = route_pdf_text(path)
            return _build_extraction_result(parse_bl_text(text), text, ocr_provider, mode)
        if provider == "mock":
            raise ValueError("Image uploads require OpenAI OCR. Set OCR_PROVIDER=openai and OPENAI_API_KEY.")
        text, mode = extract_text_with_openai(path, pdf_image=False)
        return _build_extraction_result(parse_bl_text(text), text, "openai", mode)
    except Exception as exc:
        return {
            **EXTRACTION_SCHEMA_DEFAULTS,
            "ocr_provider": provider,
            "ocr_mode": "extraction_failed",
            "ocr_error": str(exc),
        }


def route_pdf_text(path: Path) -> tuple[str, str, str]:
    """Try embedded PDF text first; fall back to OpenAI image OCR when empty or slow."""
    provider = os.getenv("OCR_PROVIDER", "openai").lower()

    if _pdf_likely_scanned(path):
        if provider == "mock":
            raise ValueError("Scanned PDF requires OpenAI OCR. Set OCR_PROVIDER=openai and OPENAI_API_KEY.")
        text, mode = extract_text_with_openai(path, pdf_image=True)
        return text, mode, "openai"

    timeout_sec = float(os.getenv("OCR_TEXT_PDF_TIMEOUT_SEC", "5"))
    text, timed_out = _extract_text_pdf_timed(path, timeout_sec)
    if not timed_out and text.strip():
        return text, "text_pdf", "pypdf" if provider != "mock" else "mock"

    if provider == "mock":
        raise ValueError("Scanned PDF requires OpenAI OCR. Set OCR_PROVIDER=openai and OPENAI_API_KEY.")
    text, mode = extract_text_with_openai(path, pdf_image=True)
    return text, mode, "openai"


def _pdf_likely_scanned(path: Path) -> bool:
    """Fast probe: skip the timed text pass when pages look image-only."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if not reader.pages:
            return True
        for page in reader.pages[: min(len(reader.pages), 3)]:
            if len((page.extract_text() or "").strip()) > 30:
                return False
        return True
    except Exception:
        return True


def _extract_text_pdf_timed(path: Path, timeout_sec: float) -> tuple[str, bool]:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(extract_text_pdf, path)
        try:
            return future.result(timeout=timeout_sec), False
        except FuturesTimeoutError:
            return "", True


def _build_extraction_result(fields: dict, text: str, provider: str, mode: str) -> dict:
    structured = {}
    if os.getenv("OCR_PROVIDER", "openai").lower() == "openai" and os.getenv("OPENAI_API_KEY"):
        try:
            structured = extract_structured_bl_json(text)
        except Exception as exc:
            structured = {"structured_ocr_error": str(exc)}
    merged = normalize_extraction_fields({**fields, **structured})
    return {
        **EXTRACTION_SCHEMA_DEFAULTS,
        **merged,
        "raw_text": text[:12000],
        "ocr_provider": provider,
        "ocr_mode": mode,
    }


def extract_structured_bl_json(text: str) -> dict:
    """Ask the configured AI model to return the full BL/AWB customs schema."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_BL_EXTRACTION_MODEL", os.getenv("OPENAI_OCR_MODEL", "gpt-5.4-mini"))
    store = os.getenv("OPENAI_OCR_STORE", "false").lower() == "true"
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": STRUCTURED_BL_EXTRACTION_PROMPT},
                    {"type": "input_text", "text": f"Document text:\n{text[:30000]}"},
                ],
            }
        ],
        store=store,
    )
    return _json_object_from_text(response.output_text or "")


def _json_object_from_text(value: str) -> dict:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else {}
    return data if isinstance(data, dict) else {}


def normalize_extraction_fields(fields: dict) -> dict:
    data = dict(fields or {})
    document_type = _clean_missing(data.get("document_type") or data.get("doc_type"))
    transport_mode = _normalize_transport_mode(data.get("transport_mode"))
    bl_type = _normalize_bl_type(data.get("bl_type"), data)
    route_type = _route_from_bl_type(bl_type, data.get("route_type"))
    zra_regime = _clean_missing(data.get("zra_regime")) or _zra_regime_from_bl_type(bl_type)
    category = normalize_gn83_category(data.get("gn83_category"), data)

    no_containers = _number_or_none(data.get("no_of_containers", data.get("no_containers")), integer=True)
    gross_weight = _number_or_none(data.get("gross_weight_mt", data.get("gross_weight")))
    gn83_fee = _number_or_none(data.get("gn83_fee_usd"))
    if gn83_fee is None and category not in {None, MISSING_STRING}:
        gn83_fee = _gn83_fee(route_type, transport_mode, category, no_containers, gross_weight)

    normalized = {
        **data,
        "bl_type": bl_type or MISSING_STRING,
        "agent_license": _clean_missing(data.get("agentLicense") or data.get("agent_license")) or MISSING_STRING,
        "agentLicense": _clean_missing(data.get("agentLicense") or data.get("agent_license")) or MISSING_STRING,
        "currency": _normalize_currency(data.get("currency")),
        "company_name": _clean_missing(data.get("company_name")) or MISSING_STRING,
        "consignor_tin": _clean_missing(data.get("consignor_tin")) or MISSING_STRING,
        "declarant_number": _clean_missing(data.get("declarant_number") or data.get("agentLicense")) or MISSING_STRING,
        "consignment_value": _number_or_none(data.get("consignment_value")),
        "document_type": document_type or MISSING_STRING,
        "doc_type": document_type or "Bill of Lading",
        "transport_mode": transport_mode or "Sea",
        "route_type": route_type or "Import",
        "zra_regime": zra_regime or "IM4 Home Use",
        "consignee": _clean_missing(data.get("consignee") or data.get("consignee_name")) or MISSING_STRING,
        "consignee_name": _clean_missing(data.get("consignee") or data.get("consignee_name")) or MISSING_STRING,
        "no_of_containers": no_containers,
        "no_containers": no_containers,
        "gross_weight_mt": gross_weight,
        "gross_weight": gross_weight,
        "gn83_category": category or "LOOSE_LCL",
        "gn83_unit": _clean_missing(data.get("gn83_unit")) or _gn83_unit_for_category(category) or MISSING_STRING,
        "gn83_fee_usd": gn83_fee,
    }
    return {key: value for key, value in normalized.items() if value is not None or key in EXTRACTION_SCHEMA_DEFAULTS}


def _ocr_pages(file_path: Path, *, pdf_image: bool | None = None):
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        if pdf_image is not True:
            text_pdf = extract_text_pdf(file_path)
            if text_pdf.strip():
                return [], "text_pdf", text_pdf
        return pdf_to_images(file_path), "image_pdf_ocr", None

    from PIL import Image

    return [Image.open(file_path).convert("RGB")], "image_ocr", None


def extract_text_with_openai(file_path: Path, *, pdf_image: bool | None = None) -> tuple[str, str]:
    pages, mode, text_pdf = _ocr_pages(file_path, pdf_image=pdf_image)
    if text_pdf is not None:
        return text_pdf, mode

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for OpenAI OCR on scanned PDFs/images.")

    if not pages:
        return "", mode

    max_workers = max(1, min(int(os.getenv("OPENAI_OCR_MAX_WORKERS", "3")), len(pages)))
    if len(pages) == 1 or max_workers == 1:
        chunks = [_openai_ocr_page_text(page, index=1, api_key=api_key)]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            chunks = list(
                executor.map(
                    lambda item: _openai_ocr_page_text(item[1], index=item[0], api_key=api_key),
                    enumerate(pages, start=1),
                )
            )

    return "\n\n".join(chunk for chunk in chunks if chunk.strip()), mode


def _openai_ocr_page_text(page, *, index: int, api_key: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_OCR_MODEL", "gpt-5.4-mini")
    store = os.getenv("OPENAI_OCR_STORE", "false").lower() == "true"
    encoded = base64.b64encode(_encode_page_image(page)).decode("ascii")
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{encoded}",
                    },
                    {
                        "type": "input_text",
                        "text": (
                            f"Extract ALL text from Bill of Lading page {index} exactly as it appears. "
                            "Preserve headings, tables, labels, values, and line breaks. "
                            "Do not summarize. Return raw extracted text only."
                        ),
                    },
                ],
            }
        ],
        store=store,
    )
    return response.output_text or ""


def _encode_page_image(page) -> bytes:
    from PIL import Image

    image = page.convert("RGB")
    max_width = int(os.getenv("OPENAI_OCR_MAX_WIDTH", "1800"))
    if image.width > max_width:
        ratio = max_width / float(image.width)
        image = image.resize((max_width, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    quality = int(os.getenv("OPENAI_OCR_JPEG_QUALITY", "82"))
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def extract_text_pdf(file_path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def pdf_to_images(file_path: Path):
    dpi = int(os.getenv("OPENAI_OCR_DPI", "200"))
    max_pages = max(1, int(os.getenv("OPENAI_OCR_MAX_PAGES", "2")))
    path = Path(file_path)
    if not path.is_file():
        raise ValueError(f"PDF not found: {path}")

    fitz_error: Exception | None = None
    try:
        import fitz
        from PIL import Image

        doc = fitz.open(str(path))
        pages = []
        for page in doc[:max_pages]:
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            pages.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        if pages:
            return pages
    except Exception as exc:
        fitz_error = exc

    try:
        from pdf2image import convert_from_path

        return convert_from_path(str(path), dpi=dpi, first_page=1, last_page=max_pages)
    except Exception as poppler_exc:
        details = [f"PyMuPDF failed: {fitz_error}" if fitz_error else "PyMuPDF returned no pages."]
        details.append(f"pdf2image/poppler failed: {poppler_exc}")
        details.append("Install poppler-utils (apt) or fix PyMuPDF for scanned PDF OCR.")
        raise ValueError(" ".join(details)) from poppler_exc


def parse_bl_text(text: str) -> dict:
    raw = text or ""
    normalized = re.sub(r"[ \t]+", " ", raw)
    fields = {
        "bl_number": first_match(
            raw,
            [
                r"B/L[- ]?No\.?\s*([A-Z]{3,5}[0-9]{8,})",
                r"B/L-No\.?:\s*\n?\s*([A-Z]{3,5}[0-9]{8,})",
                r"\bB/L[- ]?No\.?\s*[:\s]*([A-Z]{2,5}[0-9]{6,})",
                r"\b(?:BL|B/L|Bill of Lading)\s*(?:No\.?|Number|#)?\s*[:\-]?\s*([A-Z0-9\-/]{5,})",
            ],
        ),
        "consignee_name": block_match(
            raw,
            [
                r"Consignee\s*(?:\([^)]*\))?\s*:\s*\n\s*([^\n]+)",
                r"Notify Address\s*:\s*\n\s*([^\n]+)",
                r"Consignee\s*[:\-]?\s*([^\n\r]+)",
            ],
        ),
        "consignee_tin": first_match(raw, [r"\b(?:TPIN|TIN|Tax ID)\s*[:\-]?\s*([0-9A-Z\-]{6,})"]),
        "shipper_name": block_match(raw, [r"Shipper\s*:\s*\n\s*([^\n]+)"]),
        "carrier_name": first_match(
            raw,
            [
                r"^Carrier\s*:\s*([^\n]+)",
                r"Carrier\s*[:\-]?\s*([^\n\r]+)",
                r"B/L No\.\s*[A-Z0-9]+\s+([A-Z][A-Z0-9 /&\.]+)",
            ],
        ),
        "vessel_vehicle_no": first_match(
            raw,
            [
                r"Vessel\(s\)\s*:\s*\n?\s*([^\n]+)",
                r"VESSEL NAME\s*:\s*([^\n]+)",
                r"\bVessel\s*[:\-]?\s*([^\n]+)",
            ],
        ),
        "origin": first_match(
            raw,
            [
                r"Place of Receipt\s*:\s*\n?\s*([^\n]+)",
                r"Port of Loading\s*:\s*\n?\s*([^\n]+)",
                r"\b(?:Port of Loading|Place of Receipt|Origin)\s*[:\-]?\s*([^\n\r]+)",
            ],
        ),
        "destination": first_match(
            raw,
            [
                r"Port of Discharge\s*:\s*\n?\s*([^\n]+)",
                r"Place of Delivery\s*:\s*\n?\s*([^\n]+)",
                r"\b(?:Port of Discharge|Final Destination|Destination)\s*[:\-]?\s*([^\n\r]+)",
            ],
        ),
        "gross_weight": parse_gross_weight_mt(raw),
        "no_containers": int_match(
            raw,
            [
                r"Total Containers received by Carrier\s*:\s*([0-9]+)",
                r"(\d+)\s*X\s*20",
                r"(\d+)\s*X\s*40",
                r"\b(\d+)\s*CNTR\b",
                r"\b(?:Containers?|No\. of Containers?)\s*[:\-]?\s*([0-9]+)",
            ],
        ),
        "cargo_description": first_match(
            raw,
            [
                r"1X\d+'?\s*CONTAINER:\s*([^\n]+)",
                r"FCL CONTAINER:\s*\n[^\n]+\n[^\n]+\n([^\n]+)",
                r"CONTAINER CONTAINING\s*\n\s*([^\n]+)",
                r"CONTAINING\s*\n\s*([^\n]+)",
                r"LOOSE CARGO[^\n]*\n\s*([^\n]+)",
                r"\b(?:Description of Goods|Goods Description|Cargo Description)\s*[:\-]?\s*([^\n\r]+)",
            ],
        ),
        "hs_code": first_match(normalized, [r"\bHS\s*Code\s*[:\-]?\s*([0-9.]{4,})"]),
    }
    cleaned = {key: clean_value(value) for key, value in fields.items() if value not in {None, ""}}
    if cleaned.get("bl_number"):
        cleaned["bl_number"] = re.sub(r"[^A-Z0-9\-/]", "", str(cleaned["bl_number"]).upper())
    if cleaned.get("consignee_name") and _is_boilerplate_party(cleaned["consignee_name"]):
        cleaned.pop("consignee_name", None)
    if cleaned.get("vessel_vehicle_no") and len(str(cleaned["vessel_vehicle_no"])) <= 3:
        cleaned.pop("vessel_vehicle_no", None)
    if cleaned.get("cargo_description") and _is_boilerplate_cargo(cleaned["cargo_description"]):
        cleaned.pop("cargo_description", None)
    cleaned["gn83_category"] = infer_gn83_category(raw, cleaned)
    return cleaned


def parse_gross_weight_mt(text: str) -> float | None:
    anchor = re.search(r"Total Containers received by Carrier", text, flags=re.IGNORECASE)
    prefix = text[: anchor.start()] if anchor else text

    kgs_matches = re.findall(r"([0-9,]+\.[0-9]+)\s*\n\s*KGS\b", prefix, flags=re.IGNORECASE)
    if kgs_matches:
        value = float(kgs_matches[-1].replace(",", ""))
        if value >= 500:
            return round(value / 1000, 3)
        return round(value, 3)

    mts_matches = re.findall(r"GROSS\s*WT\s*:\s*([0-9,.]+)\s*MTS", prefix, flags=re.IGNORECASE)
    if len(mts_matches) == 1:
        return round(float(mts_matches[0].replace(",", "")), 3)
    if len(mts_matches) > 1:
        return round(sum(float(item.replace(",", "")) for item in mts_matches), 3)

    total_mts = first_match(prefix, [r"TOTAL GROSS WEIGHT\s*:\s*([0-9,.]+)\s*MTS"])
    if total_mts:
        return round(float(total_mts.replace(",", "")), 3)

    legacy = number_match(
        prefix,
        [
            r"TOTAL GROSS WEIGHT\s*:\s*([0-9,.]+)",
            r"Gross Weight\s*[:\-]?\s*([0-9,.]+)\s*(?:MTS|KGS|KG)\b",
        ],
    )
    if legacy is None:
        return None
    if legacy >= 500:
        return round(legacy / 1000, 3)
    return round(legacy, 3)


def infer_gn83_category(text: str, parsed: dict) -> str:
    blob = f"{text}\n{parsed.get('cargo_description', '')}".upper()
    containers = int(parsed.get("no_containers") or 0)

    if re.search(r"\b(?:IN[\s-]?HOUSE(?:\s+CLEARANCE)?|INHOUSE\s+CLEARANCE)\b", blob):
        return "IN_HOUSE_CLEARANCE"
    if re.search(r"\b(?:FERTILISER|FERTILIZER|UREA|NPK|DAP)\b", blob):
        return "FERTILIZER"
    if re.search(r"\b(?:PETROLEUM|PETROL|DIESEL|GASOLINE|LPG|CRUDE\s+OIL|JET\s+FUEL|PARAFFIN)\b", blob):
        return "PETROLEUM"
    if re.search(r"\b(?:RAW\s+SUGAR|REFINED\s+SUGAR|SUGAR)\b", blob):
        return "SUGAR"

    if re.search(r"\b(?:CHASSIS|MOTOR\s*VEHICLE|AUTOMOBILE|VEHICLE|CAR\s*PARTS)\b", blob):
        return "MOTOR_VEHICLE"
    if re.search(r"\b(?:FCL\s*\+\s*LCL|\bLCL\b|LOOSE\s*CARGO|LOOSE\s*LOT|\d+\s*LCL\b)", blob):
        return "LOOSE_LCL"
    if re.search(r"\b(?:HEAVY\s*EQUIPMENT|EXCAVATOR|CRANE|GENERATOR)\b", blob):
        return "HEAVY_EQUIPMENT"
    if re.search(r"\b(?:LIVE\s*ANIMAL|CATTLE|GOAT)\b", blob):
        return "LIVE_ANIMAL"

    nx20 = re.search(r"(\d+)\s*X\s*20", blob)
    nx40 = re.search(r"(\d+)\s*X\s*40", blob)
    count_40 = int(nx40.group(1)) if nx40 else len(re.findall(r"1X40|40\s*FT|40FT|40'", blob))
    count_20 = int(nx20.group(1)) if nx20 else len(re.findall(r"1X20|20\s*FT|20FT|20'", blob))
    if count_40 and count_40 >= max(count_20, containers, 1):
        return "40FT_CONTAINER"
    if count_20 or containers >= 1:
        if containers >= 2 and not re.search(r"\bLOOSE\b", blob):
            return "20FT_CONTAINER"
        if containers == 1 and count_20:
            return "20FT_CONTAINER"

    if re.search(r"\b(?:RICE|GRAIN|CEMENT|BULK)\b", blob):
        return "LOOSE_LCL"

    return "LOOSE_LCL" if containers <= 1 else "20FT_CONTAINER"


def block_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1)
    return None


def _is_boilerplate_party(name: str) -> bool:
    lowered = name.lower()
    return any(
        phrase in lowered
        for phrase in ("not negotiable", "unless consigned", "warranty", "particulars as declared")
    )


def _is_boilerplate_cargo(description: str) -> bool:
    lowered = description.lower()
    return any(phrase in lowered for phrase in ("gross weight", "measurement", "packages/description"))


def first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1)
    return None


def number_match(text: str, patterns: list[str]) -> float | None:
    value = first_match(text, patterns)
    if not value:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def int_match(text: str, patterns: list[str]) -> int | None:
    value = first_match(text, patterns)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def clean_value(value):
    if isinstance(value, str):
        return value.strip(" :-\t\r\n")
    return value


def _clean_missing(value) -> str | None:
    if value is None:
        return None
    text = clean_value(str(value))
    if not text or text.lower() in {"n/a", "na", "none", "unknown", "null"}:
        return None
    return text


def _number_or_none(value, *, integer: bool = False):
    if value in (None, "", MISSING_STRING):
        return None
    try:
        number = float(str(value).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None
    return int(number) if integer else round(number, 3)


def _normalize_currency(value) -> str:
    text = _clean_missing(value)
    if not text:
        return MISSING_STRING
    upper = text.upper()
    if "$" in upper:
        return "USD"
    if "€" in upper:
        return "EUR"
    if "£" in upper:
        return "GBP"
    match = re.search(r"\b(USD|EUR|GBP|ZMW|TZS|ZAR)\b", upper)
    return match.group(1) if match else upper[:3]


def _normalize_transport_mode(value) -> str | None:
    text = (_clean_missing(value) or "").upper()
    if "AIR" in text or "AWB" in text:
        return "Air"
    if "ROAD" in text or "TRUCK" in text:
        return "Road"
    if "RAIL" in text:
        return "Rail"
    if "SEA" in text or "VESSEL" in text or "BOL" in text or "LADING" in text:
        return "Sea"
    return _clean_missing(value)


def _normalize_bl_type(value, data: dict) -> str | None:
    text = (_clean_missing(value) or "").upper()
    if text.startswith(("IM", "EX", "T")):
        return text
    route = str(data.get("route_type") or data.get("document_type") or "").upper()
    if "EXPORT" in route:
        return "EX1"
    if "TRANSIT" in route:
        return "T1"
    if "IMPORT" in route:
        return "IM4"
    return None


def _route_from_bl_type(bl_type: str | None, fallback=None) -> str:
    code = (bl_type or "").upper()
    if code.startswith("EX"):
        return "Export"
    if code.startswith("T"):
        return "Transit"
    if code.startswith("IM"):
        return "Import"
    text = str(fallback or "").title()
    return text if text in {"Import", "Export", "Transit"} else "Import"


def _zra_regime_from_bl_type(bl_type: str | None) -> str:
    code = (bl_type or "").upper()
    if code.startswith("EX1"):
        return "EX1 Export"
    if code.startswith("IM7"):
        return "IM7 Warehousing"
    if code.startswith("IM8"):
        return "IM8 Temporary Import"
    if code.startswith("IM"):
        return "IM4 Home Use"
    return "Put Value"


def normalize_gn83_category(value, data: dict | None = None) -> str | None:
    data = data or {}
    text = f"{value or ''} {data.get('cargo_description') or ''}".upper()
    if not text.strip():
        return None
    if re.search(r"\b(?:IN[\s-]?HOUSE(?:\s+CLEARANCE)?|INHOUSE\s+CLEARANCE)\b", text):
        return "IN_HOUSE_CLEARANCE"
    if re.search(r"\b(?:FERTILISER|FERTILIZER|UREA|NPK|DAP)\b", text):
        return "FERTILIZER"
    if re.search(r"\b(?:PETROLEUM|PETROL|DIESEL|GASOLINE|LPG|CRUDE\s+OIL|JET\s+FUEL|PARAFFIN)\b", text):
        return "PETROLEUM"
    if re.search(r"\b(?:RAW\s+SUGAR|REFINED\s+SUGAR|SUGAR)\b", text):
        return "SUGAR"
    if "40" in text and "CONTAINER" in text:
        return "40FT_CONTAINER"
    if "20" in text and "CONTAINER" in text:
        return "20FT_CONTAINER"
    if "DRY BULK" in text or re.search(r"\b(GRAIN|COAL|CEMENT|MINERAL)\b", text):
        return "DRY_BULK"
    if "LIQUID" in text or re.search(r"\b(FUEL|OIL|CHEMICAL)\b", text):
        return "BULK_LIQUID"
    if re.search(r"\b(HS\s*87|VEHICLE|CAR|TRUCK|MOTORCYCLE)\b", text):
        return "MOTOR_VEHICLE"
    if re.search(r"\b(CRANE|EXCAVATOR|BULLDOZER|HEAVY MACHINE|PLANT EQUIPMENT)\b", text):
        return "HEAVY_EQUIPMENT"
    if re.search(r"\b(ANIMAL|LIVESTOCK|CATTLE|POULTRY LIVE)\b", text):
        return "LIVE_ANIMAL"
    if re.search(r"\b(PARCEL|COURIER|EXPRESS)\b", text):
        return "PARCEL"
    if re.search(r"\b(GOLD|PRECIOUS METAL|GEMSTONE)\b", text):
        return "PRECIOUS_MINERALS"
    if "GENERAL CARGO" in text:
        return "GENERAL_CARGO"
    if re.search(r"\b(LCL|LOOSE|LESS THAN CONTAINER)\b", text) or data.get("no_of_containers") == 0:
        return "LOOSE_LCL"
    category = _clean_missing(value)
    return category if category and category.isupper() and "_" in category else None


def _gn83_unit_for_category(category: str | None) -> str | None:
    return {
        "20FT_CONTAINER": "Container",
        "40FT_CONTAINER": "Container",
        "DRY_BULK": "MT",
        "BULK_LIQUID": "MT",
        "MOTOR_VEHICLE": "Unit",
        "HEAVY_EQUIPMENT": "Unit",
        "LIVE_ANIMAL": "BL",
        "LOOSE_LCL": "BL",
        "POST_ENTRY": "BL",
        "COASTWISE": "Transire",
        "PARCEL": "AWB",
        "GENERAL_CARGO": "AWB",
        "PRECIOUS_MINERALS": "AWB",
    }.get(category or "")


def _gn83_fee(route_type: str, transport_mode: str, category: str, no_containers, gross_weight) -> float | None:
    try:
        from services.gn83 import lookup_fee

        return lookup_fee(
            route_type,
            transport_mode,
            category,
            no_containers=no_containers,
            gross_weight=gross_weight,
        )
    except Exception:
        return None
