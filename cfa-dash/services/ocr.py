from __future__ import annotations

import base64
import io
import os
import re
from functools import lru_cache
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
    provider = os.getenv("OCR_PROVIDER", "mock").lower()
    try:
        if path.suffix.lower() == ".pdf":
            text = extract_text_pdf(path)
            if text.strip():
                return _build_extraction_result(parse_bl_text(text), text, provider, "text_pdf")
            text, ocr_mode, ocr_provider = extract_image_ocr(path, provider, pdf_image=True)
            return _build_extraction_result(parse_bl_text(text), text, ocr_provider, ocr_mode)
        text, ocr_mode, ocr_provider = extract_image_ocr(path, provider, pdf_image=False)
        return _build_extraction_result(parse_bl_text(text), text, ocr_provider, ocr_mode)
    except Exception as exc:
        return {
            **DEMO_EXTRACTION,
            "ocr_provider": provider,
            "ocr_mode": "fallback_demo",
            "ocr_error": str(exc),
        }
    return {**DEMO_EXTRACTION, "ocr_provider": provider, "ocr_mode": "demo"}


def extract_image_ocr(file_path: Path, provider: str, *, pdf_image: bool) -> tuple[str, str, str]:
    image_provider = os.getenv("OCR_IMAGE_PROVIDER", provider if provider != "mock" else "openai").lower()
    if image_provider in {"openai", "openai_api", "gpt"}:
        text, mode = extract_text_with_openai(file_path, pdf_image=pdf_image)
        return text, mode, "openai"
    if image_provider in {"tesseract", "pytesseract", "auto"}:
        text, mode = extract_text_with_tesseract(file_path, pdf_image=pdf_image)
        return text, mode, "pytesseract"
    if image_provider == "chandra":
        text, mode = extract_text_with_chandra_package(file_path, pdf_image=pdf_image)
        return text, mode, "chandra"
    raise ValueError(
        "This file has no readable PDF text. Set OCR_IMAGE_PROVIDER=openai, chandra, or pytesseract "
        "to convert it to images and run OCR."
    )


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

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_OCR_MODEL", "gpt-5.4-mini")
    store = os.getenv("OPENAI_OCR_STORE", "false").lower() == "true"
    content = []
    for idx, page in enumerate(pages, start=1):
        buffer = io.BytesIO()
        page.save(buffer, format="PNG", optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{encoded}",
            }
        )
        content.append({"type": "input_text", "text": f"--- PAGE {idx} ---"})

    content.append(
        {
            "type": "input_text",
            "text": (
                "Extract ALL text from these Bill of Lading page images exactly as it appears. "
                "Preserve headings, tables, labels, values, and line breaks. "
                "Separate pages with '--- PAGE X ---'. Do not summarize. Return raw extracted text only."
            ),
        }
    )
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": content}],
        store=store,
    )
    return response.output_text, mode


def extract_text_with_tesseract(file_path: Path, *, pdf_image: bool | None = None) -> tuple[str, str]:
    pages, mode, text_pdf = _ocr_pages(file_path, pdf_image=pdf_image)
    if text_pdf is not None:
        return text_pdf, mode

    try:
        import pytesseract
    except ImportError as exc:
        raise ValueError("pytesseract is required for scanned PDF/image OCR. Install pytesseract and Tesseract OCR.") from exc

    tesseract_cmd = os.getenv("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    lang = os.getenv("TESSERACT_LANG", "eng")
    config = os.getenv("TESSERACT_CONFIG", "--psm 6")
    chunks: list[str] = []
    for page in pages:
        text = pytesseract.image_to_string(page, lang=lang, config=config)
        if text.strip():
            chunks.append(text)
    return "\n\n".join(chunks), mode


@lru_cache(maxsize=1)
def chandra_inference_manager():
    from chandra.model import InferenceManager

    method = os.getenv("CHANDRA_METHOD", "hf").lower()
    return InferenceManager(method=method)


def extract_text_with_chandra_package(file_path: Path, *, pdf_image: bool | None = None) -> tuple[str, str]:
    pages, mode, text_pdf = _ocr_pages(file_path, pdf_image=pdf_image)
    if text_pdf is not None:
        return text_pdf, mode

    from chandra.model.schema import BatchInputItem

    manager = chandra_inference_manager()
    batch_size = max(1, int(os.getenv("CHANDRA_BATCH_SIZE", "1")))
    chunks: list[str] = []
    for start in range(0, len(pages), batch_size):
        batch = [
            BatchInputItem(image=page, prompt_type=os.getenv("CHANDRA_PROMPT_TYPE", "ocr_layout"))
            for page in pages[start : start + batch_size]
        ]
        results = manager.generate(
            batch,
            include_images=False,
            include_headers_footers=True,
        )
        for result in results:
            text = result.markdown or result.raw
            if text.strip():
                chunks.append(text)
    return "\n\n".join(chunks), mode


def extract_text_with_chandra(file_path: Path, *, pdf_image: bool | None = None) -> tuple[str, str]:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        if pdf_image is not True:
            text_pdf = extract_text_pdf(file_path)
            if text_pdf.strip():
                return text_pdf, "text_pdf"
        pages = pdf_to_images(file_path)
        mode = "image_pdf_ocr"
    else:
        from PIL import Image

        pages = [Image.open(file_path).convert("RGB")]
        mode = "image_ocr"

    pipe = chandra_pipeline()
    chunks: list[str] = []
    for page in pages:
        result = pipe(page)
        if isinstance(result, list) and result:
            chunks.append(str(result[0].get("generated_text", "")))
        else:
            chunks.append(str(result))
    return "\n\n".join(chunk for chunk in chunks if chunk.strip()), mode


def extract_text_pdf(file_path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def pdf_to_images(file_path: Path):
    try:
        import fitz
        from PIL import Image

        doc = fitz.open(str(file_path))
        pages = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), alpha=False)
            pages.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        return pages
    except Exception:
        from pdf2image import convert_from_path

        return convert_from_path(str(file_path), dpi=300)


@lru_cache(maxsize=1)
def chandra_pipeline():
    from transformers import pipeline

    model_name = os.getenv("OCR_MODEL", "datalab-to/chandra-ocr-2")
    return pipeline("image-text-to-text", model=model_name, trust_remote_code=True)


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
