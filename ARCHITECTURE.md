# ZCAMS Architecture & Agentic-Mode Design

This document describes the current architecture of the ZCAMS POC and proposes
an **Agentic Mode** that, given only a Bill of Lading file, a settlement mode,
and an importer email, can drive the entire clearance pipeline end-to-end with
zero human clicks.

The mermaid blocks below render in Cursor, GitHub, VS Code (with the
[Markdown Preview Mermaid Support](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid)
extension), and any markdown viewer that supports mermaid.

---

## 1. System context (C4 \u2014 Level 1)

Who talks to ZCAMS and what does ZCAMS talk to.

```mermaid
flowchart LR
    classDef person fill:#1f6b3b,stroke:#0d3a1f,color:#ffffff,stroke-width:1px
    classDef system fill:#7ec253,stroke:#1f6b3b,color:#0d3a1f,stroke-width:1px
    classDef external fill:#f4f9ef,stroke:#cfe5c7,color:#1c2419,stroke-width:1px

    CFA["CFA Staff<br/>(Clerk · Reviewer · Manager)"]:::person
    Importer["Importer<br/>(Consignee)"]:::person
    Zaffa["ZAFFA Admin<br/>(Super Admin)"]:::person

    ZCAMS(["ZCAMS<br/>Dash + SQLite POC"]):::system

    CapitalPay["CapitalPay<br/>Invoice signing &amp; check-out"]:::external
    Bird["Bird Reach API<br/>Email delivery"]:::external
    WhatsApp["WhatsApp Web<br/>(wa.me click-to-chat)"]:::external
    OCR["OpenAI / Groq<br/>BL OCR"]:::external
    Gmail["Gmail SMTP<br/>(fallback)"]:::external

    CFA -->|Uploads BL, reviews,<br/>requests invoice| ZCAMS
    Zaffa -->|Approves CFA<br/>onboarding| ZCAMS
    Importer -->|Receives signed invoice<br/>+ pay link| ZCAMS

    ZCAMS -->|Sign invoice,<br/>create check-out| CapitalPay
    ZCAMS -->|Send signed PDF<br/>by email| Bird
    ZCAMS -->|Deep-link to chat| WhatsApp
    ZCAMS -->|Extract BL fields| OCR
    ZCAMS -->|Onboarding emails| Gmail
```

---

## 2. Container view (C4 \u2014 Level 2)

The processes, libraries, and data stores inside ZCAMS itself.

```mermaid
flowchart TB
    classDef web fill:#1f6b3b,stroke:#0d3a1f,color:#ffffff
    classDef svc fill:#7ec253,stroke:#1f6b3b,color:#0d3a1f
    classDef data fill:#f4f9ef,stroke:#cfe5c7,color:#1c2419
    classDef ext fill:#ffffff,stroke:#cfe5c7,color:#4a4f4a,stroke-dasharray:4 3

    subgraph Browser["Browser (CFA / ZAFFA / Importer)"]
        UI["Plotly Dash UI<br/>(pages/*.py)"]:::web
    end

    subgraph Server["Python process \u2014 Dash + Flask"]
        AppPy["app.py<br/>routing, layout, auth gate"]:::web
        Pages["pages/<br/>login · onboarding · bls · reviewed_bl<br/>invoices · checkout · contracts · etc."]:::web
        Components["components/<br/>layout · workflow · icons · ui"]:::web

        Repo["services/repository.py<br/>orchestration spine<br/>(generate_invoice,<br/>share_invoice_with_importer,<br/>review_bl, detach_zsad, settle_invoice)"]:::svc
        GN83["services/gn83.py<br/>statutory fee schedule"]:::svc
        PDF["services/pdf_service.py<br/>ReportLab invoice renderer"]:::svc
        OcrAdapter["services/ocr.py<br/>BL field extractor"]:::svc
        CPay["services/capitalpay.py<br/>sign + check-out"]:::svc
        BirdSvc["services/bird_email.py"]:::svc
        Messaging["services/messaging.py<br/>WhatsApp / SMS / mailto links"]:::svc
        Chat["services/chat_service.py<br/>GN-aware FAQ + optional Qwen LLM"]:::svc
        Routes["services/invoice_routes.py<br/>Flask /download/invoice/&lt;id&gt;.pdf"]:::web
    end

    subgraph Storage["Persistent storage"]
        DB[("SQLite<br/>cfa-dash/data/zcams.db")]:::data
        Uploads[("Uploads<br/>cfa-dash/uploads/*.pdf")]:::data
        Generated[("Signed invoice PDFs<br/>cfa-dash/generated_pdfs/")]:::data
        Logs[("invoice_flow.log")]:::data
    end

    subgraph External["External services"]
        CapitalPayExt["CapitalPay API"]:::ext
        BirdExt["Bird Reach API"]:::ext
        OcrExt["OpenAI / Groq"]:::ext
        WaExt["WhatsApp wa.me"]:::ext
    end

    UI <-->|HTTP / WebSocket| AppPy
    AppPy --> Pages
    Pages --> Components
    Pages --> Repo
    Repo --> GN83
    Repo --> PDF
    Repo --> OcrAdapter
    Repo --> CPay
    Repo --> BirdSvc
    Repo --> Messaging
    Repo --> DB
    PDF --> Generated
    Pages --> Uploads
    Repo --> Logs

    CPay --> CapitalPayExt
    BirdSvc --> BirdExt
    OcrAdapter --> OcrExt
    Messaging --> WaExt

    Routes --> Repo
    Routes --> Generated

    Pages --> Chat
```

---

## 3. Data model (ER diagram)

The SQLite schema as it stands today. Cancellation, audit, and notification
tables are shown but unrelated to the core clearance pipeline.

```mermaid
erDiagram
    COMPANIES ||--o{ USERS : "employs"
    COMPANIES ||--o{ CERTIFICATES : "holds"
    COMPANIES ||--o{ BILLS_OF_LADING : "owns"
    COMPANIES ||--o{ CONTRACTS : "signs"

    BILLS_OF_LADING ||--o{ CARGO_ITEMS : "contains"
    BILLS_OF_LADING ||--o{ CONTAINERS : "carries"
    BILLS_OF_LADING ||--|| REVIEWED_BLS : "reviewed_as"

    REVIEWED_BLS ||--o{ Z_SADS : "issues (single-use)"
    REVIEWED_BLS ||--o{ INVOICES : "billed_by"

    INVOICES ||--o{ PAYMENTS : "paid_by"
    Z_SADS  ||--o{ INVOICES : "referenced_by"

    USERS ||--o{ AUDIT_EVENTS : "performs"
    COMPANIES ||--o{ NOTIFICATIONS : "receives"
    COMPANIES ||--o{ SUPPORT_TICKETS : "files"

    COMPANIES {
        TEXT id PK
        TEXT name
        TEXT tpin
        TEXT zra_licence
        TEXT zaffa_number
        TEXT status
    }
    USERS {
        TEXT id PK
        TEXT company_id FK
        TEXT email UK
        TEXT role
    }
    BILLS_OF_LADING {
        TEXT id PK
        TEXT company_id FK
        TEXT bl_number UK
        TEXT route_type
        TEXT transport_mode
        TEXT zra_regime
        TEXT consignee_name
        TEXT consignee_tin
        TEXT status
    }
    REVIEWED_BLS {
        TEXT id PK
        TEXT bl_id FK
        TEXT z_sad_id FK
        TEXT status
    }
    Z_SADS {
        TEXT id PK
        TEXT reviewed_bl_id FK
        TEXT z_sad_number UK
        INT  is_active
        INT  is_used
    }
    INVOICES {
        TEXT id PK
        TEXT reviewed_bl_id FK
        TEXT z_sad_id FK
        TEXT invoice_number UK
        TEXT invoice_type
        REAL std_min_fee
        REAL admin_fee
        REAL vat
        REAL total
        TEXT capitalpay_urn
        TEXT checkout_url
        TEXT status
    }
    PAYMENTS {
        TEXT id PK
        TEXT invoice_id FK
        REAL amount
        TEXT status
        TEXT capitalpay_ref
        TEXT settled_at
    }
```

---

## 4. Current (manual) clearance flow

A sequence diagram of the nine-stage pipeline as it runs today. Every blue arrow
that originates from `Clerk` is a *human click*.

```mermaid
sequenceDiagram
    autonumber
    actor Clerk as CFA Clerk
    participant UI as Dash UI
    participant Repo as services.repository
    participant OCR as services.ocr
    participant GN83 as services.gn83
    participant CPay as CapitalPay
    participant PDF as pdf_service
    participant Bird as Bird Reach
    participant Wa as WhatsApp wa.me
    actor Importer

    Clerk->>UI: Upload BL PDF
    UI->>Repo: create_bl(payload)
    Repo->>OCR: extract_bl_fields(file)
    OCR-->>Repo: extracted dict
    Repo->>GN83: lookup_fee(route, mode, category)
    Repo-->>UI: BL row + min_fee
    Clerk->>UI: Click "Review BL"
    UI->>Repo: review_bl(bl_id)
    Repo-->>UI: Z-SAD number issued
    Clerk->>UI: Click "Request Invoice"
    UI->>UI: Modal asks Service vs Full
    Clerk->>UI: Pick mode, enter email/phone
    UI->>Repo: generate_invoice(reviewed_id, mode, ...)
    Repo->>GN83: gn83_quote_for_reviewed()
    Repo->>CPay: create_signed_invoice(...)
    CPay-->>Repo: urn + checkout_url
    Repo->>PDF: generate_invoice_pdf(draft)
    PDF-->>Repo: pdf path
    Repo-->>UI: invoice row
    UI->>Repo: share_invoice_with_importer(channels)
    Repo->>Bird: send email + attachment
    Repo-->>UI: wa.me link
    UI->>Wa: window.open(link)
    Wa-->>Importer: WhatsApp draft
    Bird-->>Importer: Signed PDF email
    Importer->>CPay: Pays via check-out link
    CPay-->>Repo: settlement webhook (or manual sync)
    Repo->>Repo: settle_invoice() \u2192 release cargo
```

---

## 5. Proposed Agentic Mode (end-to-end autonomous)

Same diagram, but a single `AgentOrchestrator` replaces every human click after
the upload. The CFA submits **one form** with three inputs: BL file,
settlement mode (`SERVICE_FEE_ONLY` or `FULL_SETTLEMENT`), and the importer
email. Everything else is decided by deterministic business rules plus a small
LLM-assisted extraction step.

```mermaid
sequenceDiagram
    autonumber
    actor Clerk as CFA Clerk
    participant UI as Dash UI (single form)
    participant Agent as AgentOrchestrator
    participant Repo as services.repository
    participant OCR as services.ocr
    participant LLM as Verifier LLM<br/>(optional)
    participant CPay as CapitalPay
    participant Bird as Bird Reach
    participant Wa as WhatsApp wa.me
    actor Importer

    Clerk->>UI: Submit { BL pdf, mode, importer_email }
    UI->>Agent: start_run(input)
    Note over Agent: All steps idempotent &<br/>persisted in agent_runs / agent_steps
    Agent->>OCR: extract_bl_fields(pdf)
    OCR-->>Agent: candidate fields
    Agent->>LLM: validate &amp; normalise fields<br/>(route, mode, regime, HS)
    LLM-->>Agent: corrected fields + confidence
    Agent->>Agent: confidence < threshold ? \u2192 PAUSE &amp; notify clerk
    Agent->>Repo: create_bl(payload, auto_review=True)
    Repo-->>Agent: BL + reviewed_bl + Z-SAD
    Agent->>Repo: generate_invoice(reviewed_id, mode, beneficiary?)
    Repo->>CPay: create_signed_invoice(...)
    CPay-->>Repo: signed invoice
    Repo-->>Agent: invoice row + checkout_url
    Agent->>Repo: share_invoice_with_importer([EMAIL, WHATSAPP])
    Repo->>Bird: send signed PDF + pay link
    Repo-->>Agent: wa.me link
    Agent->>Wa: queue WhatsApp link for clerk (or skip)
    Agent-->>UI: run status \"AWAITING_PAYMENT\"
    Bird-->>Importer: signed PDF + pay link
    Importer->>CPay: settles
    CPay-->>Agent: webhook /agent/settlement
    Agent->>Repo: settle_invoice(id)
    Repo-->>Agent: cargo_release issued
    Agent-->>UI: run status \"CARGO_RELEASED\"
    Agent-->>Clerk: completion notification
```

---

## 6. Proposed Agentic Mode \u2014 component view

Where Agentic Mode plugs into the existing container diagram.

```mermaid
flowchart LR
    classDef new fill:#fff3c4,stroke:#a07a00,color:#3a2f00,stroke-width:1.2px
    classDef existing fill:#7ec253,stroke:#1f6b3b,color:#0d3a1f

    Form["pages/agent_run.py<br/>(new) single-form launcher"]:::new
    Agent["services/agent.py<br/>(new) AgentOrchestrator<br/>plan \u2192 act \u2192 verify \u2192 persist"]:::new
    Verifier["services/agent_verifier.py<br/>(new) LLM field-validator<br/>+ confidence gate"]:::new
    Runs[("agent_runs / agent_steps tables<br/>(new)")]:::new
    Webhook["services/agent_webhooks.py<br/>(new) /agent/settlement &amp; replay"]:::new

    Repo["services.repository<br/>(existing \u2014 unchanged)"]:::existing
    GN83["services.gn83"]:::existing
    CPay["services.capitalpay"]:::existing
    Bird["services.bird_email"]:::existing
    OCR["services.ocr"]:::existing

    Form --> Agent
    Agent --> Verifier
    Verifier --> OCR
    Agent --> Repo
    Repo --> GN83
    Repo --> CPay
    Repo --> Bird
    Agent --> Runs
    Webhook --> Agent
    CPay -.->|settlement callback| Webhook
```

---

## 7. Agent state machine

Each `agent_run` row moves through a small, auditable state machine. Any state
can transition to `FAILED` or `PAUSED_FOR_REVIEW` so a human can take over.

```mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> OCR_EXTRACTED : OCR + LLM verify
    OCR_EXTRACTED --> PAUSED_FOR_REVIEW : confidence &lt; threshold
    PAUSED_FOR_REVIEW --> OCR_EXTRACTED : clerk approves fields
    OCR_EXTRACTED --> BL_CREATED : repository.create_bl
    BL_CREATED --> REVIEWED : repository.review_bl
    REVIEWED --> INVOICE_SIGNED : generate_invoice + CapitalPay
    INVOICE_SIGNED --> SHARED : share_invoice_with_importer
    SHARED --> AWAITING_PAYMENT : Bird email + WhatsApp dispatched
    AWAITING_PAYMENT --> SETTLED : CapitalPay webhook
    AWAITING_PAYMENT --> REMINDED : dunning ladder T+3 / T+7
    REMINDED --> SETTLED : CapitalPay webhook
    SETTLED --> CARGO_RELEASED : settle_invoice cascade
    CARGO_RELEASED --> [*]

    SUBMITTED --> FAILED
    OCR_EXTRACTED --> FAILED
    BL_CREATED --> FAILED
    INVOICE_SIGNED --> FAILED
    SHARED --> FAILED
    FAILED --> [*]
```
