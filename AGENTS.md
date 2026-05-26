# ZCAMS POC Context

Persistent project context for agents.

## Current Direction

The active app is `cfa-dash/`, a Plotly Dash POC for ZAFFA Clearing &
Forwarding. The product is **ZCAMS**: Zambia Customs Agent Management System.

The POC follows the architecture document:

1. CFA onboarding and ZAFFA approval
2. Bill of Lading upload / capture
3. Reviewed BL
4. Z-SAD generation
5. GN 83 invoice calculation
6. CapitalPay Check-out
7. Payment settlement
8. Cargo release
9. Contracts, certificates, profile, notifications, support, and chat

There is no Single Use Certificate workflow in the active app. Use **Z-SAD**
terminology throughout.

## Storage

The POC uses SQLite, initialized automatically at startup:

```text
cfa-dash/data/zcams.db
```

Main persistence files:

- `cfa-dash/services/schema.sql`
- `cfa-dash/services/db.py`
- `cfa-dash/services/repository.py`

## Integrations

Adapters are present but mock/configured-placeholder by default:

- `cfa-dash/services/capitalpay.py`
- `cfa-dash/services/ocr.py`
- `cfa-dash/services/messaging.py`
- `cfa-dash/services/pdf_service.py`

Real CapitalPay signing/check-out, OpenAI/Groq OCR, and Gmail SMTP can be
enabled through `.env` once credentials and API docs are supplied.

ZCAMS Chat uses `services/chat_service.py`. It is Gazette Notice-aware in
fallback mode by default. The optional local small-model path uses
`transformers` with `CHAT_MODEL_NAME=unsloth/Qwen2.5-0.5B-Instruct` and is
enabled only when `CHAT_MODEL_ENABLED=true`.

## Navigation

The architecture modules are:

- Login (`/login`) and CFA Onboarding (`/onboarding`)
- Dashboard
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

Do not add modules outside the architecture unless the user explicitly asks.

## Run

From workspace root:

```powershell
.\run-zcams.ps1
```

Tests:

```powershell
.\test-zcams.ps1
```

The Windows shell wrapper may print `Add-Content : Stream was not readable`.
Ignore that wrapper noise when the actual command status/output is successful.
