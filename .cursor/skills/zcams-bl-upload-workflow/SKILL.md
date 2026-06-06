---
name: zcams-bl-upload-workflow
description: Applies ZCAMS procedural memory for the Bill of Lading journey: upload/capture, text-PDF vs scanned-PDF OCR, human review, GN 83 counter-checking, Z-SAD issuance, invoice generation, and sharing by email or WhatsApp. Use when the user mentions BL upload, BL OCR, reviewed BLs, GN83, containers, LCL/loose cargo, CapitalPay invoices, importer links, email/WhatsApp sharing, or end-to-end BL workflow tests.
disable-model-invocation: true
---

# ZCAMS BL Upload Workflow

This skill captures the agent's procedural memory for the ZCAMS Bill of Lading user journey, from uploading a BL up to sending the resulting invoice/link to the importer by email or WhatsApp.

## Memory Anchor

The user's intended flow is operational, not just technical: an agent uploads a BL, ZCAMS extracts draft data, the agent reviews and corrects it, GN 83 is used to counter-check the right billing category, the BL is saved, a Z-SAD is issued, an invoice is generated, and the importer receives a practical link or email/WhatsApp message containing the invoice/PDF/payment route.

Treat OCR as a draft assistant. Never assume OCR is final. The agent must compare the original BL to the populated form before saving.

## User Journey

1. Agent opens `BLs` at `/bls`.
2. Agent uploads a BL PDF/image/Word document.
3. ZCAMS shows upload progress: upload, scan pages, run OCR, validate BL fields, prepare for review.
4. ZCAMS fills the BL capture form with draft values.
5. Agent reviews every important field against the source BL.
6. Agent checks GN 83 category against the cargo/container facts.
7. Agent saves the BL.
8. Agent moves to invoice/Z-SAD handling, either through the post-save `Request invoice` step or `Reviewed BL`.
9. ZCAMS issues a Z-SAD after review.
10. Agent generates a agency-charge or full-settlement invoice.
11. Agent shares the invoice with the importer by WhatsApp link or email, including PDF download/payment information.

## OCR Decision Memory

For uploaded PDFs, first try embedded text extraction:

- If `extract_text_pdf` returns usable text, continue as `text_pdf`.
- If the PDF has no readable text, convert pages to images with PyMuPDF (`fitz`) and pass those images to the configured OCR adapter.
- The current image-PDF route prefers OpenAI OCR when `OCR_IMAGE_PROVIDER=openai`; Tesseract and Chandra are alternative adapters.
- OCR must return raw text, then `parse_bl_text` extracts BL fields.
- If OCR fails, the fallback demo values are only placeholders and must not be treated as verified BL data.

## Review Fields

Before saving, verify:

- `BL Number`
- `Document type`
- `Route`
- `Transport mode`
- `ZRA regime`
- `Consignee`
- `Consignee TIN`
- `Origin`
- `Destination`
- `No. of containers`
- `Gross weight (MT)`
- `Cargo description`
- `GN 83 category`

## Five-Value Re-Check

Before saving the BL, generating the invoice, or sending the email/WhatsApp link, ask the user or agent to re-check the five values that determine whether the BL, invoice, and send-out message are correct:

1. `BL Number` - this identifies the shipment and links the BL to the reviewed BL, Z-SAD, invoice, PDF, and share message.
2. `Consignee/Consigner TIN` - confirm the tax identifier used for the importer/customer record is correct.
3. `Gross Weight (MT)` - this supports cargo validation and may affect GN 83 interpretation for bulk or loose cargo.
4. `No. of containers / loose cargo / LCL` - confirm whether the shipment is full-container cargo or loose/consolidated/LCL cargo before applying GN 83.
5. `Full Settlement` - confirm the invoice type before generating and sending the invoice.

If any of these five values are uncertain, stop and ask the user to re-check the BL before continuing. Do not send the mail/WhatsApp link until these five values are confirmed.

## GN 83 Reasoning

Use `services.gn83.lookup_fee`, `gn83_quote_for_reviewed`, and `calculate_invoice` as the source of truth.

For Import + Sea, remember:

| BL type | Category | Standard minimum |
| --- | --- | --- |
| 1 x 20FT container | `20FT_CONTAINER` | USD 150 |
| 10 x 20FT containers | `20FT_CONTAINER` | USD 1,500 |
| Loose / consolidated / LCL | `LOOSE_LCL` | USD 90 flat |

Category decision:

- Full container BLs normally use `20FT_CONTAINER` or `40FT_CONTAINER`.
- Loose cargo, consolidated cargo, LCL, loose lots, and mixed `FCL + LCL` should use `LOOSE_LCL`.
- LCL/loose cargo is not multiplied by container count in GN 83 billing.
- For container categories, standard minimum is per billable container/unit.

Invoice calculation memory:

- - `FULL_SETTLEMENT`: subtotal = standard minimum + admin fee; VAT = 16% of subtotal; total is ceiled.

## Episodic Test Memory

These are the tests already exercised in this project and should guide future changes.

### Episode 1: BL1, one container

Source:

```text
C:\Users\cwakh\Downloads\CapitalPay_BLs_TestDocs\CapitalPay_BLs\k_lekey\BL1_1Container_MSC_MSC4051473322.pdf
```

Observed and expected:

- BL number: `MSC4051473322`
- OCR mode: `text_pdf`
- OCR provider during test: `mock`, because the PDF already had readable text
- Consignee: `ETS ARAKA`
- Containers: `1`
- Gross weight: `27.065`
- Cargo contains: `LONG GRAIN WHITE RICE`
- GN 83 category: `20FT_CONTAINER`
- Standard minimum: `USD 150`
- Full Settlement total: `USD 35`
- Full Settlement total: `USD 209`
- WhatsApp share link starts with `https://wa.me/`
- Email fallback link starts with `mailto:` when live email is not being tested
- Share message contains `Download PDF:`

### Episode 2: BL4, ten containers

Source:

```text
C:\Users\cwakh\Downloads\CapitalPay_BLs_TestDocs\CapitalPay_BLs\k_lekey\BL4_10Containers_HAPAG-LLOYD_HLCU1443330589.pdf
```

Observed and expected:

- BL number: `HLCU1443330589`
- OCR mode: `text_pdf`
- OCR provider during test: `mock`, because the PDF already had readable text
- Consignee: `ETS ARAKA`
- Containers: `10`
- Gross weight: `270.65`
- Cargo contains: `LONG GRAIN WHITE RICE`
- GN 83 category: `20FT_CONTAINER`
- Standard minimum: `USD 1,500`
- Full Settlement total: `USD 348`
- Full Settlement total: `USD 2,088`
- WhatsApp link starts with `https://wa.me/`
- Email link starts with `mailto:` when live email is not configured
- Share message contains `Download PDF:`

### Episode 3: LCL / loose cargo guardrail

Existing fixture-backed cases:

- `BL3_3Containers_1Loose_CMA CGM_CMAU1839718662.txt`
- `BL5_4LCL_1Container_EVERGREEN_EITU7350316991.txt`

Expected memory:

- GN 83 category must be `LOOSE_LCL`.
- Standard minimum must not multiply by container count.
- Import + Sea loose/LCL standard minimum is `USD 90`.
- Full Settlement total for USD 90 standard minimum is `USD 21`.
- Full Settlement total for USD 90 standard minimum is `USD 126`.

### Episode 4: End-to-end share path

The tested path created BLs, auto-reviewed them, generated Z-SADs, generated service invoices, and verified invoice PDF/download/share semantics.

When validating share output, confirm:

- `invoice_share_message` contains invoice number, BL number, Z-SAD, amount due, CapitalPay invoice number, and `Download PDF:`.
- `invoice_whatsapp_link` returns a WhatsApp URL.
- `invoice_email_link` returns a mailto URL when live sending is not configured.
- `share_invoice_with_importer(..., channels=["EMAIL"])` attaches the invoice PDF when SMTP/Bird is configured and `ensure_invoice_pdf` succeeds.

## Agent Action Pattern

When implementing, debugging, or testing this journey:

1. Identify whether the problem is in upload/OCR, field parsing, GN 83 classification, BL save, reviewed BL/Z-SAD, invoice generation, or sharing.
2. Reproduce with the smallest BL case first (`BL1_1Container...`), then the high-count case (`BL4_10Containers...`).
3. Add or update tests around the business invariant, not only the UI symptom.
4. For LCL/loose cargo, assert category and amount together so container-count multiplication cannot silently regress.
5. Validate share semantics without sending live email unless the user explicitly asks for a live send.
6. Preserve the user's language: ZCAMS, BL, Reviewed BL, Z-SAD, GN 83, CapitalPay, importer, WhatsApp, email.

## Useful Test Commands

From `cfa-dash/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ocr.py tests\test_gn83_containers.py tests\test_bl_e2e.py -q --basetemp=.pytest-tmp\bl-workflow-skill
```

Focused parse check for the two `k_lekey` PDFs:

```powershell
$env:CAPITALPAY_MODE='mock'
$env:OCR_PROVIDER='mock'
.\.venv\Scripts\python.exe -c "from pathlib import Path; from services.ocr import extract_bl_fields; files=[r'C:\Users\cwakh\Downloads\CapitalPay_BLs_TestDocs\CapitalPay_BLs\k_lekey\BL4_10Containers_HAPAG-LLOYD_HLCU1443330589.pdf', r'C:\Users\cwakh\Downloads\CapitalPay_BLs_TestDocs\CapitalPay_BLs\k_lekey\BL1_1Container_MSC_MSC4051473322.pdf']; [print(Path(f).name, {k: extract_bl_fields(str(Path(f))).get(k) for k in ['bl_number','ocr_mode','no_containers','gross_weight','gn83_category','consignee_name']}) for f in files]"
```

## Safety And Boundaries

- Do not force duplicate BL reuse unless the old BL/Z-SAD journey is eligible for cancellation.
- Do not detach or replace Z-SAD after payment settlement, release pending, or cargo released.
- Do not send live email in tests unless the user explicitly requests live email. Prefer mailto-link validation or mock mode.
- Preserve Z-SAD terminology. Do not introduce Single Use Certificate wording.
- Do not treat the test PDFs as secret, but do not expose API keys or `.env` credentials while testing OCR/email.
