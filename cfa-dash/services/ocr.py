from __future__ import annotations

import base64
import io
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
            **DEMO_EXTRACTION,
            "ocr_provider": provider,
            "ocr_mode": "fallback_demo",
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
    merged = {**DEMO_EXTRACTION, **fields}
    return {
        **merged,
        "raw_text": text[:12000],
        "ocr_provider": provider,
        "ocr_mode": mode,
    }


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
    try:
        import fitz
        from PIL import Image

        doc = fitz.open(str(file_path))
        pages = []
        for page in doc[:max_pages]:
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            pages.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        return pages
    except Exception:
        from pdf2image import convert_from_path

        return convert_from_path(str(file_path), dpi=dpi, first_page=1, last_page=max_pages)


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

    if re.search(r"\b(?:RICE|GRAIN|FERTILIZER|CEMENT|BULK)\b", blob):
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
