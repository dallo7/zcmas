from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from services import ocr
from services.ocr import extract_text_pdf, extract_bl_fields, parse_bl_text

MSC_BL_PDF = Path(
    r"c:\Users\cwakh\Downloads\CapitalPay_BLs_TestDocs\CapitalPay_BLs\j_patrick\BL1_1Container_MSC_MSC8466112528.pdf"
)


def test_parse_msc_bl_sample_text():
    text = (Path(__file__).resolve().parent / "fixtures" / "msc_bl_sample.txt").read_text(encoding="utf-8")
    parsed = parse_bl_text(text)
    assert parsed["bl_number"] == "MSC8466112528"
    assert parsed["consignee_name"] == "ETS ARAKA"
    assert parsed["shipper_name"] == "PAGARIYA EXPORTS PRIVATE LIMITED"
    assert parsed["vessel_vehicle_no"] == "MSC ZANZIBAR"
    assert parsed["origin"] == "NAGPUR ICD, INDIA"
    assert parsed["destination"] == "DAR-ES-SALAAM"
    assert parsed["gross_weight"] == 27.065
    assert parsed["no_containers"] == 1
    assert "PARBOILED RICE" in parsed["cargo_description"]


def test_extract_capitalpay_msc_bl_pdf(monkeypatch):
    if not MSC_BL_PDF.is_file():
        pytest.skip("MSC sample PDF not available")
    text = extract_text_pdf(MSC_BL_PDF)
    assert "MSC8466112528" in text
    monkeypatch.setenv("OCR_PROVIDER", "openai")
    result = extract_bl_fields(str(MSC_BL_PDF))
    assert result["bl_number"] == "MSC8466112528"
    assert result["consignee_name"] == "ETS ARAKA"
    assert result["ocr_mode"] == "text_pdf"


def test_parse_maersk_two_container_bl():
    text = (Path(__file__).resolve().parent / "fixtures" / "BL2_2Containers_MAERSK_MAEU0662766336.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    parsed = parse_bl_text(text)
    assert parsed["bl_number"] == "MAEU0662766336"
    assert parsed["no_containers"] == 2
    assert parsed["gn83_category"] == "20FT_CONTAINER"
    assert parsed["gross_weight"] == 54.13


def test_image_pdf_routes_through_openai_ocr(monkeypatch, tmp_path):
    pdf_path = tmp_path / "image-only-bl.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 image-only placeholder")

    monkeypatch.setenv("OCR_PROVIDER", "openai")
    monkeypatch.setattr(ocr, "extract_text_pdf", lambda _path: "")
    monkeypatch.setattr(ocr, "pdf_to_images", lambda _path: [object()])
    monkeypatch.setattr(
        ocr,
        "extract_text_with_openai",
        lambda _path, pdf_image=False: ("Bill of Lading No: IMG123456 Consignee: Image Importer", "image_pdf_ocr"),
    )

    result = extract_bl_fields(str(pdf_path))

    assert result["ocr_provider"] == "openai"
    assert result["ocr_mode"] == "image_pdf_ocr"
    assert result["bl_number"] == "IMG123456"


def test_pdf_router_uses_text_pdf_when_fast_text(monkeypatch, tmp_path):
    pdf_path = tmp_path / "text-bl.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    monkeypatch.setenv("OCR_PROVIDER", "openai")
    monkeypatch.setattr(ocr, "_pdf_likely_scanned", lambda _path: False)

    def fail_openai(*_args, **_kwargs):
        raise AssertionError("OpenAI OCR should not run for fast text PDFs")

    monkeypatch.setattr(ocr, "extract_text_pdf", lambda _path: "Bill of Lading No: TXT123456 Consignee: Text Importer")
    monkeypatch.setattr(ocr, "extract_text_with_openai", fail_openai)

    result = extract_bl_fields(str(pdf_path))

    assert result["ocr_provider"] == "pypdf"
    assert result["ocr_mode"] == "text_pdf"
    assert result["bl_number"] == "TXT123456"


def test_pdf_router_falls_back_when_text_extraction_is_slow(monkeypatch, tmp_path):
    import time

    pdf_path = tmp_path / "slow-bl.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    monkeypatch.setenv("OCR_PROVIDER", "openai")
    monkeypatch.setenv("OCR_TEXT_PDF_TIMEOUT_SEC", "0.1")
    monkeypatch.setattr(ocr, "_pdf_likely_scanned", lambda _path: False)

    def slow_extract(_path):
        time.sleep(1)
        return "Bill of Lading No: LATE123456"

    monkeypatch.setattr(ocr, "extract_text_pdf", slow_extract)
    monkeypatch.setattr(
        ocr,
        "extract_text_with_openai",
        lambda _path, pdf_image=False: ("Bill of Lading No: IMG999999 Consignee: Image Importer", "image_pdf_ocr"),
    )

    result = extract_bl_fields(str(pdf_path))

    assert result["ocr_provider"] == "openai"
    assert result["ocr_mode"] == "image_pdf_ocr"
    assert result["bl_number"] == "IMG999999"


def test_parse_cma_three_container_loose_bl():
    text = (Path(__file__).resolve().parent / "fixtures" / "BL3_3Containers_1Loose_CMA CGM_CMAU1839718662.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    parsed = parse_bl_text(text)
    assert parsed["bl_number"] == "CMAU1839718662"
    assert parsed["no_containers"] == 3
    assert parsed["gn83_category"] == "LOOSE_LCL"
    assert parsed["gross_weight"] == 96.345


def test_parse_evergreen_fcl_lcl_bl():
    text = (Path(__file__).resolve().parent / "fixtures" / "BL5_4LCL_1Container_EVERGREEN_EITU7350316991.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    parsed = parse_bl_text(text)
    assert parsed["bl_number"] == "EITU7350316991"
    assert parsed["gn83_category"] == "LOOSE_LCL"
    assert parsed["gross_weight"] == 47.865
