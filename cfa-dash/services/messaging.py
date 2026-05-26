from __future__ import annotations

import os
import smtplib
import mimetypes
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

from services.bird_email import bird_email_enabled, send_bird_email


def normalize_zambia_phone(phone: str | None) -> str:
    raw = "".join(ch for ch in (phone or "") if ch.isdigit())
    if raw.startswith("0"):
        raw = raw[1:]
    if not raw.startswith("260"):
        raw = "260" + raw
    return raw


def whatsapp_url(phone: str | None, message: str) -> str:
    return f"https://wa.me/{normalize_zambia_phone(phone)}?text={quote(message)}"


def sms_url(phone: str | None, message: str) -> str:
    return f"sms:{normalize_zambia_phone(phone)}?body={quote(message)}"


def mailto_url(email: str | None, subject: str, body: str) -> str:
    target = (email or "").strip()
    if not target:
        return ""
    return f"mailto:{target}?subject={quote(subject)}&body={quote(body)}"


def send_sms(phone: str, message: str) -> dict:
    api_url = os.getenv("SMS_API_URL", "").strip()
    if not api_url:
        return {"sent": False, "mode": "mock", "reason": "SMS API not configured", "link": sms_url(phone, message)}
    return {"sent": True, "mode": "api", "reason": "SMS API integration pending"}


def _send_gmail_smtp(
    to_email: str,
    subject: str,
    body: str,
    *,
    html: str | None = None,
    attachments: list[Path] | None = None,
    attachment_names: list[str] | None = None,
) -> dict:
    host = os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("GMAIL_SMTP_PORT", "587"))
    user = os.getenv("GMAIL_SMTP_USER", "")
    password = os.getenv("GMAIL_SMTP_PASSWORD", "")
    sender = os.getenv("GMAIL_FROM_EMAIL", user)

    if not user or not password:
        return {"sent": False, "mode": "mock", "reason": "Gmail SMTP credentials missing"}

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")

    for idx, attachment in enumerate(attachments or []):
        path = Path(attachment)
        if not path.is_file():
            return {"sent": False, "mode": "gmail", "reason": f"Attachment missing: {path.name}"}
        mime_type, _encoding = mimetypes.guess_type(path.name)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        filename = (
            attachment_names[idx]
            if attachment_names and idx < len(attachment_names) and attachment_names[idx]
            else path.name
        )
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=filename)

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    return {"sent": True, "mode": "gmail"}


def send_email(
    to_email: str,
    subject: str,
    body: str,
    *,
    html: str | None = None,
    recipient_name: str | None = None,
    attachments: list[Path] | None = None,
    attachment_names: list[str] | None = None,
    description: str = "ZCAMS email",
) -> dict:
    """Send email via Bird API when configured, otherwise Gmail SMTP, otherwise mock."""
    target = (to_email or "").strip()
    if not target:
        return {"sent": False, "mode": "mock", "reason": "No recipient email"}

    if bird_email_enabled():
        return send_bird_email(
            target,
            subject,
            body,
            html=html,
            recipient_name=recipient_name,
            attachments=attachments,
            attachment_names=attachment_names,
            description=description,
        )

    return _send_gmail_smtp(
        target,
        subject,
        body,
        html=html,
        attachments=attachments,
        attachment_names=attachment_names,
    )


def onboarding_approval_email(
    *,
    company_name: str,
    contact_name: str,
    to_email: str,
    username: str,
    password: str,
    login_url: str,
) -> tuple[str, str, str]:
    subject = f"ZCAMS — {company_name} approved"
    text = (
        f"Dear {contact_name},\n\n"
        f"Your CFA registration for {company_name} has been approved by ZAFFA.\n\n"
        f"ZCAMS login credentials:\n"
        f"  Login URL: {login_url}\n"
        f"  Username: {username}\n"
        f"  Email: {to_email}\n"
        f"  Temporary password: {password}\n\n"
        "Sign in and change your password after first login.\n\n"
        "Regards,\nZCAMS — Zambia Customs Agent Management System"
    )
    html = (
        f"<p>Dear <strong>{contact_name}</strong>,</p>"
        f"<p>Your CFA registration for <strong>{company_name}</strong> has been approved by ZAFFA.</p>"
        f"<table style='border-collapse:collapse;margin:16px 0'>"
        f"<tr><td style='padding:6px 12px;font-weight:600'>Login URL</td><td style='padding:6px 12px'><a href='{login_url}'>{login_url}</a></td></tr>"
        f"<tr><td style='padding:6px 12px;font-weight:600'>Username</td><td style='padding:6px 12px'>{username}</td></tr>"
        f"<tr><td style='padding:6px 12px;font-weight:600'>Email</td><td style='padding:6px 12px'>{to_email}</td></tr>"
        f"<tr><td style='padding:6px 12px;font-weight:600'>Temporary password</td><td style='padding:6px 12px'><code>{password}</code></td></tr>"
        f"</table>"
        f"<p>Sign in and change your password after first login.</p>"
        f"<p>Regards,<br/><strong>ZCAMS</strong> — Zambia Customs Agent Management System</p>"
    )
    return subject, text, html


def invoice_share_email(
    *,
    recipient_name: str,
    message: str,
    invoice_number: str,
) -> tuple[str, str, str]:
    subject = f"ZCAMS Invoice {invoice_number}"
    text = message
    html = (
        f"<p>Dear <strong>{recipient_name}</strong>,</p>"
        f"<p>Please find your ZCAMS customs invoice <strong>{invoice_number}</strong> attached.</p>"
        f"<pre style='white-space:pre-wrap;font-family:inherit;background:#f5fbf3;padding:12px;border-radius:8px'>"
        f"{message}</pre>"
        f"<p>Regards,<br/><strong>ZCAMS</strong></p>"
    )
    return subject, text, html
