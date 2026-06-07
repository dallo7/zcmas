#!/usr/bin/env python3
"""Run on the server to debug scanned/image BL PDF OCR.

Usage:
  cd /root/zcmas/cfa-dash
  source .venv/bin/activate
  python scripts/diagnose_ocr.py /path/to/your-bl.pdf
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/diagnose_ocr.py /path/to/bl.pdf")
        return 1

    pdf = Path(sys.argv[1]).expanduser().resolve()
    section("Environment")
    print("cwd:", os.getcwd())
    print("pdf:", pdf)
    print("pdf exists:", pdf.is_file())
    if pdf.is_file():
        print("pdf size bytes:", pdf.stat().st_size)
    print("OPENAI_API_KEY set:", bool(os.getenv("OPENAI_API_KEY")))
    print("OCR_PROVIDER:", os.getenv("OCR_PROVIDER", "(unset)"))

    section("Dependencies")
    try:
        import fitz  # noqa: F401

        print("PyMuPDF import: OK")
    except Exception as exc:
        print("PyMuPDF import: FAIL", exc)

    try:
        from pdf2image import convert_from_path  # noqa: F401

        print("pdf2image import: OK")
    except Exception as exc:
        print("pdf2image import: FAIL", exc)

    import shutil

    print("poppler (pdftoppm):", shutil.which("pdftoppm") or "NOT IN PATH")

    if not pdf.is_file():
        print("\nERROR: PDF path does not exist. Upload the file first or pass the real path.")
        return 1

    section("Scanned PDF probe")
    from services import ocr

    print("likely_scanned:", ocr._pdf_likely_scanned(pdf))

    section("Render PDF pages (PyMuPDF / poppler fallback)")
    try:
        pages = ocr.pdf_to_images(pdf)
        print("pages rendered:", len(pages))
        if pages:
            print("first page size:", pages[0].size)
    except Exception as exc:
        print("RENDER FAILED:", exc)
        traceback.print_exc()
        return 1

    section("OpenAI page OCR (first page only)")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("SKIP: OPENAI_API_KEY missing")
        return 1
    try:
        t0 = time.time()
        text, mode = ocr.extract_text_with_openai(pdf, pdf_image=True)
        print(f"mode={mode} elapsed={time.time() - t0:.1f}s text_len={len(text)}")
        print("preview:", (text or "")[:500])
    except Exception as exc:
        print("OPENAI OCR FAILED:", exc)
        traceback.print_exc()
        return 1

    section("Full BL field extraction")
    try:
        t0 = time.time()
        result = ocr.extract_bl_fields(str(pdf))
        print(f"elapsed={time.time() - t0:.1f}s")
        for key in (
            "ocr_mode",
            "ocr_provider",
            "ocr_error",
            "bl_number",
            "consignee_name",
            "gross_weight",
            "no_containers",
            "gn83_category",
        ):
            print(f"{key}: {result.get(key)!r}")
    except Exception as exc:
        print("EXTRACT FAILED:", exc)
        traceback.print_exc()
        return 1

    if result.get("ocr_mode") == "extraction_failed":
        return 1
    print("\nOK: image PDF OCR pipeline succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
