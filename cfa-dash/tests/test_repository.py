from services.gn83 import calculate_invoice, lookup_fee
from services.repository import (
    DEMO_COMPANY_ID,
    bootstrap,
    contract_fingerprint,
    create_contract,
    parse_shipment_details,
    generate_zsad_number,
    invoice_capitalpay_number,
    invoice_share_message,
    list_invoices_for_user,
    send_contract_to_importer,
    send_contract_review_email,
    sign_contract_with_otp,
)


def test_generate_zsad_number_format():
    number = generate_zsad_number("BL-ZM-KBCX")
    prefix, suffix, random_part = number.split("-")[0:2], number.split("-")[2], number.split("-")[3]

    assert "-".join(prefix) == "Z-SAD"
    assert suffix == "KBCX"
    assert len(random_part) == 15
    assert sum(ch.isdigit() for ch in random_part) == 9
    assert sum(ch.isalpha() for ch in random_part) == 6
    assert "0" not in random_part


def test_gn83_lookup_and_invoice_calculation():
    std = lookup_fee("Import", "Sea", "MOTOR_VEHICLE")
    full = calculate_invoice(std, "FULL_SETTLEMENT")
    service = calculate_invoice(std, "SERVICE_FEE_ONLY")

    assert std == 130.0
    assert full == {"std_min_fee": 130.0, "admin_fee": 26.0, "vat": 24.96, "total": 181.0}
    assert service == {"std_min_fee": 130.0, "admin_fee": 26.0, "vat": 4.16, "total": 31.0}


def test_invoice_share_message_uses_gn83_total():
    msg = invoice_share_message(
        {
            "id": "inv-test",
            "invoice_number": "INV-TEST",
            "invoice_type": "SERVICE_FEE_ONLY",
            "bl_number": "BL1",
            "z_sad_number": "Z-SAD-1",
            "total": 35.0,
            "payable_amount": 35.0,
            "capitalpay_urn": "CPAYTEST",
        }
    )
    assert "Amount due: USD 35.00" in msg
    assert "CapitalPay checkout:" not in msg


def test_invoice_capitalpay_number_prefers_payment_ref():
    assert invoice_capitalpay_number({"capitalpay_ref": "CPAYABC", "capitalpay_urn": "urn:xyz"}) == "CPAYABC"
    assert invoice_capitalpay_number({"capitalpay_urn": "urn:xyz"}) == "urn:xyz"


def test_list_invoices_for_user_scopes_by_company():
    super_rows = list_invoices_for_user({"role": "SUPER_ADMIN", "company_id": DEMO_COMPANY_ID})
    company_rows = list_invoices_for_user({"role": "COMPANY_ADMIN", "company_id": DEMO_COMPANY_ID})
    assert len(super_rows) >= len(company_rows)
    assert all(row.get("company_id") == DEMO_COMPANY_ID for row in company_rows)


def test_contract_signing_requires_otp_and_stores_fingerprint():
    bootstrap()
    contract = create_contract(
        "OTP Importer Ltd",
        "260971555555",
        "otp-importer@example.com",
        "Importer authorizes the agent to clear the shipment.",
        shipment_details="1x40ft container from Dar es Salaam to Lusaka.",
        services="Customs clearance, document handling, delivery coordination.",
        fees="Service fee USD 250 plus statutory disbursements.",
        company_id=DEMO_COMPANY_ID,
    )

    signed = sign_contract_with_otp(
        contract_no=contract["contract_no"],
        email="otp-importer@example.com",
        otp=contract["otp"],
        signature_name="Jane Importer",
        signature_text="Jane Importer",
    )

    assert signed["status"] == "SIGNED"
    assert signed["signed_email"] == "otp-importer@example.com"
    assert len(signed["contract_hash"]) == 64
    tampered_hash = contract_fingerprint(
        {**signed, "fees": "Service fee USD 251 plus statutory disbursements."},
        signed_email=signed["signed_email"],
        signature_name=signed["signature_name"],
        signature_text=signed["signature_text"],
    )
    assert tampered_hash != signed["contract_hash"]


def test_contract_send_blocks_immediate_duplicate_email(monkeypatch):
    bootstrap()
    sent = []

    def fake_send_email(*args, **kwargs):
        sent.append(args)
        return {"sent": True, "mode": "test"}

    monkeypatch.setattr("services.repository.send_email", fake_send_email)
    contract = create_contract(
        "Duplicate Guard Importer",
        "260971555556",
        "duplicate-guard@example.com",
        "Standard terms.",
        shipment_details='{"shipment_route":"Mombasa -> Nairobi -> Kampala"}',
        company_id=DEMO_COMPANY_ID,
    )

    first = send_contract_to_importer(contract["id"])
    second = send_contract_to_importer(contract["id"])

    assert first["email"]["sent"] is True
    assert second["email"]["mode"] == "dedupe"
    assert len(sent) == 1


def test_contract_review_email_sends_otp_and_pdf_attachment(monkeypatch):
    bootstrap()
    captured = {}

    def fake_send_email(to_email, subject, body, **kwargs):
        captured["to_email"] = to_email
        captured["subject"] = subject
        captured["body"] = body
        captured["attachments"] = kwargs.get("attachments")
        captured["attachment_names"] = kwargs.get("attachment_names")
        return {"sent": True, "mode": "test"}

    monkeypatch.setattr("services.repository.send_email", fake_send_email)
    contract = create_contract(
        "Attachment Importer",
        "260971555557",
        "attachment-importer@example.com",
        "Standard terms.",
        shipment_details='{"shipment_route":"Mombasa -> Nairobi -> Kampala"}',
        company_id=DEMO_COMPANY_ID,
    )

    result = send_contract_review_email(contract["id"], attach_pdf=True)

    assert result["email"]["sent"] is True
    assert result["attached_pdf"] is True
    assert "OTP:" in captured["body"]
    assert "Use the OTP sent" not in captured["body"]
    assert captured["attachments"] and captured["attachments"][0].is_file()
    assert captured["attachment_names"][0].endswith(".pdf")


def test_parse_structured_contract_shipment_details():
    parsed = parse_shipment_details(
        '{"shipment_route":"Mombasa -> Nairobi -> Kampala","bl_reference":"BL-2024-KE-00472","cargo":"Electronics"}'
    )

    assert parsed["shipment_route"] == "Mombasa -> Nairobi -> Kampala"
    assert parsed["bl_reference"] == "BL-2024-KE-00472"
    assert parsed["cargo"] == "Electronics"
