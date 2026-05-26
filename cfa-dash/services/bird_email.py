"""Bird Reach API email delivery for ZCAMS."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import requests


def bird_email_enabled() -> bool:
    mode = os.getenv("BIRD_EMAIL_MODE", "mock").strip().lower()
    if mode == "mock":
        return False
    return bool(os.getenv("BIRD_EMAIL_ACCESS_KEY", "").strip() and bird_api_url())


def bird_api_url() -> str:
    return os.getenv(
        "BIRD_EMAIL_API_URL",
        "https://email.us-west-2.api.bird.com/api/workspaces/56453b27-2796-4d91-ae4a-3c2578c6bc20/reach/transmissions",
    ).strip()


def bird_from() -> dict:
    return {
        "email": os.getenv("BIRD_EMAIL_FROM", "no_reply@zcams.info").strip() or "no_reply@zcams.info",
        "name": os.getenv("BIRD_EMAIL_FROM_NAME", "ZCAMS").strip() or "ZCAMS",
    }


def _encode_attachment(path: Path, filename: str | None = None) -> dict:
    name = filename or path.name
    content_type = "application/pdf" if name.lower().endswith(".pdf") else "application/octet-stream"
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {"name": name, "type": content_type, "data": data}


def send_bird_email(
    to_email: str,
    subject: str,
    text: str,
    *,
    html: str | None = None,
    recipient_name: str | None = None,
    attachments: list[Path] | None = None,
    attachment_names: list[str] | None = None,
    description: str = "ZCAMS transmission",
) -> dict:
    """Send email via Bird Reach API."""
    if not bird_email_enabled():
        return {
            "sent": False,
            "mode": "mock",
            "reason": "Bird email API not configured (set BIRD_EMAIL_MODE=api and BIRD_EMAIL_ACCESS_KEY)",
        }

    access_key = os.getenv("BIRD_EMAIL_ACCESS_KEY", "").strip()
    payload_attachments = []
    for index, path in enumerate(attachments or []):
        if not path.is_file():
            continue
        alias = None
        if attachment_names and index < len(attachment_names):
            alias = attachment_names[index]
        payload_attachments.append(_encode_attachment(path, alias))

    payload = {
        "recipients": [
            {
                "address": {"email": to_email.strip(), "name": recipient_name or to_email.strip()},
                "rcpt_type": "to",
            }
        ],
        "content": {
            "from": bird_from(),
            "subject": subject,
            "text": text,
            "html": html or f"<p>{text.replace(chr(10), '<br/>')}</p>",
        },
        "description": description,
    }
    if payload_attachments:
        payload["content"]["attachments"] = payload_attachments

    headers = {
        "Authorization": f"AccessKey {access_key}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(bird_api_url(), headers=headers, data=json.dumps(payload), timeout=45)
        body = response.json() if response.content else {}
        if response.status_code >= 400:
            return {
                "sent": False,
                "mode": "bird",
                "status_code": response.status_code,
                "reason": body.get("message") or body.get("error") or response.text or "Bird API error",
                "response": body,
            }
        return {
            "sent": True,
            "mode": "bird",
            "status_code": response.status_code,
            "response": body,
        }
    except requests.RequestException as exc:
        return {"sent": False, "mode": "bird", "reason": str(exc)}
