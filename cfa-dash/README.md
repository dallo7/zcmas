# ZCAMS Dash POC

ZCAMS (Zambia Customs Agent Management System) is a Plotly Dash POC for
ZAFFA Clearing & Forwarding. It supports CFA onboarding, Bill of Lading
review, Z-SAD generation, GN 83 fee enforcement, invoicing, Check-out,
contracts, certificates, notifications, support, and a FAQ chat module.

## Run

From the workspace root:

```powershell
.\run-zcams.ps1
```

Then open:

```text
http://127.0.0.1:8050/
```

## Test

```powershell
.\test-zcams.ps1
```

## Storage

The POC uses SQLite:

```text
cfa-dash/data/zcams.db
```

The database is created automatically when the Dash app starts.

## Main Modules

- Dashboard
- CFA Onboarding
- BLs
- Reviewed BL
- Invoices
- Check-out
- Contracts
- Certificates
- Company Profile
- Notifications
- Support
- ZCAMS Chat
- GN 83 Schedule

## Key Rules Implemented

- BL number uniqueness
- Z-SAD number format and uniqueness
- Z-SAD detachment retires the old number and cancels old invoices
- GN 83 minimum fee lookup for Import, Export, and Transit
- Full Settlement invoice formula: standard minimum + 20% admin + 16% VAT on subtotal (ceiled)
- Service Fee Only invoice formula: 20% admin fee + 16% VAT on admin fee (ceiled)
- Full Settlement auto-releases cargo after payment settlement
- Service Fee Only enables manual cargo release after payment settlement
- Notifications and audit records are persisted

## Integrations

Real integrations are behind adapters and can be enabled once credentials and
API documentation are supplied:

- `services/capitalpay.py` for invoice signing and Check-out links
- `services/ocr.py` for OpenAI/Groq BL extraction
- `services/messaging.py` for WhatsApp click-to-chat and Gmail SMTP
- `services/chat_service.py` for Gazette Notice-aware ZCAMS Chat. It uses
  fallback FAQ mode by default and can load `unsloth/Qwen2.5-0.5B-Instruct`
  through HuggingFace Transformers when `CHAT_MODEL_ENABLED=true`.

See `.env.example` for configuration placeholders.
