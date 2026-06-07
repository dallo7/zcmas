from __future__ import annotations

import os
import random
import base64
import binascii
import hashlib
import html as html_tools
import io
import json
import re
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from services import capitalpay
from services.chat_service import answer_question, clear_document_cache
from services.db import DATA_DIR, UPLOAD_DIR, connect, init_db, rows_to_dicts
from services.gn83 import billable_units, calculate_invoice, gn83_quote_for_reviewed, lookup_fee
from services.messaging import (
    invoice_share_email,
    mailto_url,
    new_user_registration_email,
    onboarding_approval_email,
    send_email,
    send_new_user_registration_email,
    send_sms,
    whatsapp_url,
)
from services.ocr import extract_bl_fields
from services.pdf_service import generate_invoice_pdf


DEMO_COMPANY_ID = "company-zaffa-demo"
DEMO_USER_ID = "user-admin-demo"
DEMO_PASSWORD = "demo123"
ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
DEFAULT_CONTRACT_TERMS_PATH = ASSETS_DIR / "tcams_contract_terms.txt"

BL_CANCEL_REASONS = (
    "Uploaded by Mistake",
    "BL has an Issue",
    "Importer Cancelled",
    "Other",
)

BL_CANCELLED_SUFFIX = "::CANCELLED::"

# Declarant and Agent are the same operational role; AGENT is normalized to DECLARANT.
OPERATIONAL_ROLE = "DECLARANT"
LEGACY_AGENT_ROLE = "AGENT"

DEMO_USERS = [
    {
        "id": "user-super-admin-demo",
        "first_name": "Super",
        "last_name": "Admin",
        "email": "superadmin@zcams.co.zm",
        "username": "superadmin",
        "phone": "971234560",
        "whatsapp": "971234560",
        "role": "SUPER_ADMIN",
    },
    {
        "id": DEMO_USER_ID,
        "first_name": "Company",
        "last_name": "Admin",
        "email": "admin@zaffa.co.zm",
        "username": "companyadmin",
        "phone": "971234567",
        "whatsapp": "971234567",
        "role": "COMPANY_ADMIN",
    },
    {
        "id": "user-agent-demo",
        "first_name": "Clearing",
        "last_name": "Agent",
        "email": "agent@zaffa.co.zm",
        "username": "agent",
        "phone": "971234568",
        "whatsapp": "971234568",
        "role": OPERATIONAL_ROLE,
    },
]


def normalize_role(role: str | None) -> str:
    """Declarant = Agent — one operational clearance role."""
    normalized = (role or OPERATIONAL_ROLE).upper()
    if normalized == LEGACY_AGENT_ROLE:
        return OPERATIONAL_ROLE
    return normalized


def is_operational_role(role: str | None) -> bool:
    return normalize_role(role) == OPERATIONAL_ROLE


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def money(value: Any) -> str:
    return f"${float(value or 0):,.2f}"


def rows(query: str, params: tuple = ()) -> list[dict]:
    with connect() as conn:
        return rows_to_dicts(conn.execute(query, params).fetchall())


def row(query: str, params: tuple = ()) -> dict | None:
    result = rows(query, params)
    return result[0] if result else None


def execute(query: str, params: tuple = ()) -> None:
    with connect() as conn:
        conn.execute(query, params)
        conn.commit()


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    password_salt = secrets.token_hex(16) if salt is None else salt
    digest = hashlib.sha256(f"{password_salt}:{password}".encode("utf-8")).hexdigest()
    return digest, password_salt


def safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "document")
    return cleaned.strip("._") or "document"


def store_uploaded_document(company_id: str, filename: str, contents: str | None = None) -> str:
    company_dir = UPLOAD_DIR / company_id
    company_dir.mkdir(parents=True, exist_ok=True)
    target = company_dir / safe_filename(filename)
    if contents and "," in contents:
        try:
            target.write_bytes(base64.b64decode(contents.split(",", 1)[1]))
        except (binascii.Error, ValueError):
            target.write_text("Invalid upload payload captured by ZCAMS POC.", encoding="utf-8")
    else:
        target.write_text("Document reference captured by ZCAMS POC.", encoding="utf-8")
    return str(target.relative_to(UPLOAD_DIR.parent))


def _decode_upload_contents(contents: str | None) -> bytes:
    if not contents or "," not in contents:
        raise ValueError("No upload payload was received.")
    try:
        return base64.b64decode(contents.split(",", 1)[1])
    except (binascii.Error, ValueError) as exc:
        raise ValueError("The uploaded file could not be read.") from exc


def _store_invoice_ready_logo(company_id: str, filename: str, contents: str | None) -> str:
    payload = _decode_upload_contents(contents)
    max_upload_bytes = 2 * 1024 * 1024
    if len(payload) > max_upload_bytes:
        raise ValueError("Company logo must be 2 MB or smaller.")

    try:
        from PIL import Image as PILImage
    except ImportError as exc:
        raise ValueError("Pillow is required to process company logos.") from exc

    company_dir = UPLOAD_DIR / company_id
    company_dir.mkdir(parents=True, exist_ok=True)

    try:
        with PILImage.open(io.BytesIO(payload)) as source:
            source = source.convert("RGBA")
            source.thumbnail((192, 192), PILImage.Resampling.LANCZOS)
            canvas = PILImage.new("RGBA", (192, 192), (255, 255, 255, 0))
            x = (192 - source.width) // 2
            y = (192 - source.height) // 2
            canvas.alpha_composite(source, (x, y))
    except Exception as exc:
        raise ValueError("The uploaded logo must be a valid image file.") from exc

    png_target = company_dir / "company-logo-invoice.png"
    rgb_canvas = PILImage.new("RGB", canvas.size, (255, 255, 255))
    rgb_canvas.paste(canvas, mask=canvas.getchannel("A"))

    for colors_count in (128, 64, 32, 16):
        buffer = io.BytesIO()
        quantized = rgb_canvas.quantize(colors=colors_count)
        quantized.save(buffer, format="PNG", optimize=True)
        if len(buffer.getvalue()) <= 15 * 1024:
            png_target.write_bytes(buffer.getvalue())
            return str(png_target.relative_to(UPLOAD_DIR.parent))

    jpg_target = company_dir / "company-logo-invoice.jpg"
    for quality in (75, 60, 45, 32):
        buffer = io.BytesIO()
        rgb_canvas.save(buffer, format="JPEG", quality=quality, optimize=True)
        if len(buffer.getvalue()) <= 15 * 1024 or quality == 32:
            jpg_target.write_bytes(buffer.getvalue())
            return str(jpg_target.relative_to(UPLOAD_DIR.parent))

    jpg_target.write_bytes(buffer.getvalue())
    return str(jpg_target.relative_to(UPLOAD_DIR.parent))


def ensure_demo_users() -> None:
    with connect() as conn:
        for user in DEMO_USERS:
            password_hash, password_salt = hash_password(DEMO_PASSWORD)
            conn.execute(
                """
                INSERT OR IGNORE INTO users (
                  id, company_id, first_name, last_name, username, email,
                  password_hash, password_salt, phone, whatsapp, role
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    DEMO_COMPANY_ID,
                    user["first_name"],
                    user["last_name"],
                    user["username"],
                    user["email"],
                    password_hash,
                    password_salt,
                    user["phone"],
                    user["whatsapp"],
                    user["role"],
                ),
            )
            existing = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE users
                    SET username = ?, role = ?, first_name = ?, last_name = ?, email = ?,
                        phone = ?, whatsapp = ?
                    WHERE id = ?
                    """,
                    (
                        user["username"],
                        user["role"],
                        user["first_name"],
                        user["last_name"],
                        user["email"],
                        user["phone"],
                        user["whatsapp"],
                        user["id"],
                    ),
                )
            if not existing or not existing["password_hash"]:
                conn.execute(
                    "UPDATE users SET username = ?, password_hash = ?, password_salt = ? WHERE id = ?",
                    (user["username"], password_hash, password_salt, user["id"]),
                )
        conn.execute(
            "UPDATE users SET role = ? WHERE upper(role) = ?",
            (OPERATIONAL_ROLE, LEGACY_AGENT_ROLE),
        )
        conn.commit()


def ensure_demo_operational_records(company_id: str = DEMO_COMPANY_ID) -> None:
    """Keep supporting pages useful even on a freshly bootstrapped workspace."""
    if not row("SELECT id FROM contracts WHERE company_id = ? LIMIT 1", (company_id,)):
        create_contract(
            "Kabwe Mining Imports",
            "260971111111",
            "imports@kabwe-mining.example",
            "Standard ZAFFA clearing mandate for copperbelt import consignments.",
            company_id=company_id,
        )
        contract = create_contract(
            "Lusaka Logistics Ltd",
            "260972222222",
            "ops@lusaka-logistics.example",
            "Service-fee clearing support and importer payment coordination.",
            company_id=company_id,
        )
        sign_contract(contract["id"], "Lusaka Logistics Ltd")
    if len(list_certificates(company_id)) < 2:
        existing = {cert.get("name") for cert in list_certificates(company_id)}
        for name, filename in [
            ("PACRA Registration Certificate", "pacra-registration.pdf"),
            ("ZRA Customs Agent Licence", "zra-customs-agent-licence.pdf"),
        ]:
            if name not in existing:
                add_certificate(name, filename, company_id)


def bootstrap() -> None:
    init_db()
    if row("SELECT id FROM companies WHERE id = ?", (DEMO_COMPANY_ID,)):
        ensure_demo_users()
        ensure_demo_operational_records()
        return
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO companies (
              id, name, pacra_number, tpin, zra_licence, zaffa_number,
              company_email, phone, whatsapp, address_line1, city, province,
              bank_name, account_number, account_holder, status, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DEMO_COMPANY_ID,
                "ZAFFA Clearing & Forwarding",
                "120050012345",
                "1000123456",
                "ZRA/CA/2026/001",
                "ZAFFA-2026-0001",
                "admin@zaffa.co.zm",
                "971234567",
                "971234567",
                "Cairo Road",
                "Lusaka",
                "Lusaka",
                "Zanaco Bank",
                "0123456789",
                "ZAFFA Clearing & Forwarding",
                "APPROVED",
                now_iso(),
            ),
        )
        conn.execute(
            """
            INSERT INTO notifications (id, company_id, user_id, event_type, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                new_id("notif"),
                DEMO_COMPANY_ID,
                DEMO_USER_ID,
                "SYSTEM_READY",
                "ZCAMS pilot workspace initialized for ZAFFA Clearing & Forwarding.",
            ),
        )
        conn.commit()
    ensure_demo_users()
    ensure_demo_operational_records()


def list_demo_users() -> list[dict]:
    ensure_demo_users()
    return rows(
        """
        SELECT id, company_id, first_name, last_name, username, email, role, status
        FROM users
        WHERE email IN (?, ?, ?)
        ORDER BY
          CASE role
            WHEN 'SUPER_ADMIN' THEN 1
            WHEN 'COMPANY_ADMIN' THEN 2
            ELSE 3
          END
        """,
        tuple(user["email"] for user in DEMO_USERS),
    )


def authenticate_user(identifier: str | None, password: str | None) -> dict | None:
    if not identifier or not password:
        return None
    ensure_demo_users()
    user = row(
        """
        SELECT id, company_id, first_name, last_name, username, email, role, status,
               must_change_password, password_hash, password_salt
        FROM users
        WHERE (lower(email) = lower(?) OR lower(username) = lower(?)) AND status = 'ACTIVE'
        """,
        (identifier, identifier),
    )
    if not user:
        return None
    expected, _salt = hash_password(password, user.get("password_salt") or "")
    if expected != user.get("password_hash"):
        return None
    user = {key: value for key, value in user.items() if key not in {"password_hash", "password_salt"}}
    user["role"] = normalize_role(user.get("role"))
    user["must_change_password"] = bool(user.get("must_change_password"))
    return user


def change_user_password(user_id: str, current_password: str, new_password: str) -> dict:
    if not current_password or not new_password:
        raise ValueError("Current password and new password are required.")
    if len(new_password) < 8:
        raise ValueError("New password must be at least 8 characters.")
    user = row(
        """
        SELECT id, company_id, first_name, last_name, username, email, phone, whatsapp,
               role, status, password_hash, password_salt
        FROM users
        WHERE id = ? AND status = 'ACTIVE'
        """,
        (user_id,),
    )
    if not user:
        raise ValueError("Active user not found.")
    expected, _salt = hash_password(current_password, user.get("password_salt") or "")
    if expected != user.get("password_hash"):
        raise ValueError("Current password is not correct.")
    password_hash, password_salt = hash_password(new_password)
    execute(
        """
        UPDATE users
        SET password_hash = ?,
            password_salt = ?,
            must_change_password = 0,
            password_changed_at = ?
        WHERE id = ?
        """,
        (password_hash, password_salt, now_iso(), user_id),
    )
    notify("PASSWORD_CHANGED", f"Password changed for {user.get('email')}.", user_id, user.get("company_id") or DEMO_COMPANY_ID)
    audit("CHANGE_PASSWORD", "user", user_id, company_id=user.get("company_id") or DEMO_COMPANY_ID)
    updated = row(
        """
        SELECT id, company_id, first_name, last_name, username, email, phone, whatsapp,
               role, status, must_change_password
        FROM users WHERE id = ?
        """,
        (user_id,),
    ) or {}
    updated["role"] = normalize_role(updated.get("role"))
    updated["must_change_password"] = bool(updated.get("must_change_password"))
    return updated


def notify(event_type: str, message: str, related_entity_id: str | None = None, company_id: str = DEMO_COMPANY_ID) -> None:
    execute(
        """
        INSERT INTO notifications (id, company_id, user_id, event_type, message, related_entity_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (new_id("notif"), company_id, DEMO_USER_ID, event_type, message, related_entity_id),
    )


def audit(
    action_type: str,
    entity_type: str,
    entity_id: str,
    details: str = "",
    company_id: str = DEMO_COMPANY_ID,
    user_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    actor = user_id or DEMO_USER_ID
    ip = ip_address
    try:
        from flask import has_request_context

        if has_request_context():
            from services import auth

            actor = user_id or auth.current_user_id()
            ip = ip_address or auth._client_ip()
    except Exception:
        pass
    execute(
        """
        INSERT INTO audit_events (id, company_id, user_id, action_type, entity_type, entity_id, details, ip_address)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (new_id("audit"), company_id, actor, action_type, entity_type, entity_id, details, ip),
    )


def get_company(company_id: str = DEMO_COMPANY_ID) -> dict:
    return row("SELECT * FROM companies WHERE id = ?", (company_id,)) or {}


def update_registry_company(company_id: str, name: str, company_email: str = "", phone: str = "") -> dict:
    existing = get_company(company_id)
    if not existing:
        raise ValueError("Select a valid CFA company.")
    if not name:
        raise ValueError("Company name is required.")
    execute(
        "UPDATE companies SET name = ?, company_email = ?, phone = ? WHERE id = ?",
        (name.strip(), (company_email or "").strip().lower(), (phone or "").strip(), company_id),
    )
    notify("COMPANY_UPDATED", f"CFA registry details were updated for {name}.", company_id, company_id)
    audit("UPDATE_REGISTRY_COMPANY", "company", company_id, company_id=company_id)
    return get_company(company_id)


def set_registry_company_status(company_id: str, status: str) -> dict:
    existing = get_company(company_id)
    if not existing:
        raise ValueError("Select a valid CFA company.")
    normalized = (status or "").strip().upper()
    if normalized not in {"APPROVED", "SUSPENDED", "PENDING_APPROVAL"}:
        raise ValueError("Company status must be Approved, Suspended, or Pending Approval.")
    approved_at = now_iso() if normalized == "APPROVED" else existing.get("approved_at")
    execute("UPDATE companies SET status = ?, approved_at = ? WHERE id = ?", (normalized, approved_at, company_id))
    verb = {"APPROVED": "activated", "SUSPENDED": "suspended", "PENDING_APPROVAL": "moved to pending approval"}[normalized]
    notify("COMPANY_STATUS_CHANGED", f"CFA {existing.get('name')} was {verb}.", company_id, company_id)
    audit("SET_REGISTRY_COMPANY_STATUS", "company", company_id, normalized, company_id=company_id)
    return get_company(company_id)


def delete_registry_company(company_id: str) -> None:
    existing = get_company(company_id)
    if not existing:
        raise ValueError("Select a valid CFA company.")
    if company_id == DEMO_COMPANY_ID:
        raise ValueError("The default ZAFFA demo company cannot be deleted.")
    audit("DELETE_REGISTRY_COMPANY", "company", company_id, existing.get("name") or "", company_id=company_id)
    execute("DELETE FROM companies WHERE id = ?", (company_id,))


def update_company_profile(company_id: str, payload: dict) -> dict:
    allowed = [
        "name",
        "pacra_number",
        "tpin",
        "zra_licence",
        "zaffa_number",
        "year_established",
        "employee_count",
        "company_email",
        "phone",
        "whatsapp",
        "address_line1",
        "address_line2",
        "city",
        "province",
        "postal_address",
        "bank_name",
        "account_number",
        "account_holder",
        "branch",
    ]
    values = {field: payload.get(field) for field in allowed}
    assignments = ", ".join(f"{field} = ?" for field in allowed)
    execute(
        f"UPDATE companies SET {assignments} WHERE id = ?",
        tuple(values[field] for field in allowed) + (company_id,),
    )
    notify("COMPANY_PROFILE_UPDATED", "Company profile details were updated.", company_id, company_id)
    audit("UPDATE_COMPANY_PROFILE", "company", company_id, company_id=company_id)
    return get_company(company_id)


def list_companies() -> list[dict]:
    return rows("SELECT * FROM companies ORDER BY created_at DESC")


def list_company_users(company_id: str = DEMO_COMPANY_ID) -> list[dict]:
    return rows(
        """
        SELECT id, first_name, last_name, username, email, phone, whatsapp, role, status, created_at
        FROM users
        WHERE company_id = ?
        ORDER BY
          CASE role
            WHEN 'COMPANY_ADMIN' THEN 1
            WHEN 'DECLARANT' THEN 2
            ELSE 3
          END,
          created_at ASC
        """,
        (company_id,),
    )


def list_system_users(search: str | None = None) -> list[dict]:
    query = """
        SELECT u.id, u.company_id, c.name AS company_name, u.first_name, u.last_name,
               u.username, u.email, u.phone, u.whatsapp, u.role, u.status, u.created_at
        FROM users u
        LEFT JOIN companies c ON c.id = u.company_id
    """
    params: list[Any] = []
    if search:
        q = f"%{search.strip()}%"
        query += """
            WHERE u.first_name LIKE ? OR u.last_name LIKE ? OR u.username LIKE ?
               OR u.email LIKE ? OR u.role LIKE ? OR u.status LIKE ? OR c.name LIKE ?
        """
        params.extend([q, q, q, q, q, q, q])
    query += """
        ORDER BY
          CASE u.role
            WHEN 'SUPER_ADMIN' THEN 1
            WHEN 'ADMIN' THEN 2
            WHEN 'OPERATIONS' THEN 3
            WHEN 'COMPANY_ADMIN' THEN 4
            WHEN 'DECLARANT' THEN 5
            ELSE 6
          END,
          u.created_at DESC
    """
    return rows(query, tuple(params))


def get_system_user(user_id: str) -> dict:
    return row(
        """
        SELECT u.id, u.company_id, c.name AS company_name, u.first_name, u.last_name,
               u.username, u.email, u.phone, u.whatsapp, u.role, u.status, u.created_at
        FROM users u
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE u.id = ?
        """,
        (user_id,),
    ) or {}


def get_company_user(user_id: str, company_id: str = DEMO_COMPANY_ID) -> dict:
    return row(
        """
        SELECT id, company_id, first_name, last_name, username, email, phone, whatsapp, role, status, created_at
        FROM users
        WHERE id = ? AND company_id = ?
        """,
        (user_id, company_id),
    ) or {}


def update_company_user(
    user_id: str,
    company_id: str,
    first_name: str,
    last_name: str,
    email: str,
    phone: str = "",
    whatsapp: str = "",
    role: str = "DECLARANT",
) -> dict:
    if not first_name or not last_name or not email:
        raise ValueError("First name, last name, and email are required.")
    if normalize_role(role) != OPERATIONAL_ROLE:
        raise ValueError("Company Admin can only create or update Declarant users.")
    existing = get_company_user(user_id, company_id)
    if not existing:
        raise ValueError("Selected user was not found for this company.")
    if normalize_role(existing.get("role")) != OPERATIONAL_ROLE:
        raise ValueError("Company Admin can only manage Declarant users.")
    email_conflict = row(
        "SELECT id FROM users WHERE lower(email) = lower(?) AND id != ?",
        (email, user_id),
    )
    if email_conflict:
        raise ValueError("Another user already uses that email.")
    execute(
        """
        UPDATE users
        SET first_name = ?, last_name = ?, email = ?, phone = ?, whatsapp = ?, role = ?
        WHERE id = ? AND company_id = ?
        """,
        (first_name, last_name, email, phone, whatsapp, normalize_role(role), user_id, company_id),
    )
    notify("USER_UPDATED", f"ZCAMS user {first_name} {last_name} was updated.", user_id, company_id)
    audit("UPDATE_COMPANY_USER", "user", user_id, company_id=company_id)
    return get_company_user(user_id, company_id)


def set_company_user_status(user_id: str, company_id: str, status: str) -> dict:
    existing = get_company_user(user_id, company_id)
    if not existing:
        raise ValueError("Selected user was not found for this company.")
    if normalize_role(existing.get("role")) != OPERATIONAL_ROLE:
        raise ValueError("Company Admin can only manage Declarant users.")
    status = "SUSPENDED" if status == "SUSPENDED" else "ACTIVE"
    if existing.get("role") == "COMPANY_ADMIN" and status == "SUSPENDED":
        active_admins = rows(
            """
            SELECT id FROM users
            WHERE company_id = ? AND role = 'COMPANY_ADMIN' AND status = 'ACTIVE' AND id != ?
            """,
            (company_id, user_id),
        )
        if not active_admins:
            raise ValueError("You cannot suspend the last active company admin.")
    execute("UPDATE users SET status = ? WHERE id = ? AND company_id = ?", (status, user_id, company_id))
    verb = "suspended" if status == "SUSPENDED" else "activated"
    notify("USER_STATUS_CHANGED", f"ZCAMS user {existing.get('email')} was {verb}.", user_id, company_id)
    audit("SET_COMPANY_USER_STATUS", "user", user_id, status, company_id=company_id)
    return get_company_user(user_id, company_id)


def delete_company_user(user_id: str, company_id: str) -> None:
    existing = get_company_user(user_id, company_id)
    if not existing:
        raise ValueError("Selected user was not found for this company.")
    if normalize_role(existing.get("role")) != OPERATIONAL_ROLE:
        raise ValueError("Company Admin can only manage Declarant users.")
    if existing.get("role") == "COMPANY_ADMIN":
        other_admins = rows(
            """
            SELECT id FROM users
            WHERE company_id = ? AND role = 'COMPANY_ADMIN' AND id != ?
            """,
            (company_id, user_id),
        )
        if not other_admins:
            raise ValueError("You cannot delete the last company admin.")
    execute("DELETE FROM users WHERE id = ? AND company_id = ?", (user_id, company_id))
    notify("USER_DELETED", f"ZCAMS user {existing.get('email')} was deleted.", user_id, company_id)
    audit("DELETE_COMPANY_USER", "user", user_id, company_id=company_id)


def create_company_user(
    company_id: str,
    first_name: str,
    last_name: str,
    email: str,
    phone: str = "",
    whatsapp: str = "",
    role: str = "DECLARANT",
) -> dict:
    if not first_name or not last_name or not email:
        raise ValueError("First name, last name, and email are required.")
    if normalize_role(role) != OPERATIONAL_ROLE:
        raise ValueError("Company Admin can only create Declarant users.")
    if row("SELECT id FROM users WHERE lower(email) = lower(?)", (email,)):
        raise ValueError("A user with that email already exists.")
    username = re.sub(r"[^a-z0-9]+", ".", email.lower().split("@", 1)[0]).strip(".") or f"agent-{uuid.uuid4().hex[:6]}"
    base_username = username
    counter = 2
    while row("SELECT id FROM users WHERE lower(username) = lower(?)", (username,)):
        username = f"{base_username}{counter}"
        counter += 1
    password = generate_temp_password()
    password_hash, password_salt = hash_password(password)
    user_id = new_id("user")
    execute(
        """
        INSERT INTO users (
          id, company_id, first_name, last_name, username, email,
          password_hash, password_salt, must_change_password, phone, whatsapp, role
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            company_id,
            first_name,
            last_name,
            username,
            email,
            password_hash,
            password_salt,
            1,
            phone,
            whatsapp,
            normalize_role(role),
        ),
    )
    contact_name = f"{first_name} {last_name}".strip()
    registration_email = email_new_user_registration(user_id, password)
    email_result = registration_email["email_result"]
    notify("USER_CREATED", f"ZCAMS login created for {contact_name} ({email}).", user_id, company_id)
    if email_result.get("sent"):
        notify("CREDENTIALS_EMAILED", f"Login credentials emailed to {email}.", user_id, company_id)
    audit("CREATE_COMPANY_USER", "user", user_id, company_id=company_id)
    user = row(
        """
        SELECT id, company_id, first_name, last_name, username, email, phone, whatsapp,
               role, status, must_change_password, created_at
        FROM users WHERE id = ?
        """,
        (user_id,),
    ) or {}
    user["temp_password"] = registration_email["temp_password"]
    user["must_change_password"] = bool(user.get("must_change_password"))
    user["email_result"] = email_result
    return user


def create_system_user(
    company_id: str,
    first_name: str,
    last_name: str,
    email: str,
    role: str,
    phone: str = "",
    whatsapp: str = "",
    username: str = "",
    password: str = "",
) -> dict:
    if not first_name or not last_name or not email:
        raise ValueError("First name, last name, and email are required.")
    if row("SELECT id FROM companies WHERE id = ?", (company_id,)) is None:
        raise ValueError("Select a valid company for this user.")
    normalized_role = normalize_role(role)
    if normalized_role not in {"SUPER_ADMIN", "ADMIN", "OPERATIONS", "COMPANY_ADMIN", "DECLARANT"}:
        raise ValueError("Role must be Super Admin, Admin Support, Operations, Company Admin, or Declarant.")
    if row("SELECT id FROM users WHERE lower(email) = lower(?)", (email,)):
        raise ValueError("A user with that email already exists.")
    username = (username or "").strip().lower()
    if not username:
        username = re.sub(r"[^a-z0-9]+", ".", email.lower().split("@", 1)[0]).strip(".") or f"user-{uuid.uuid4().hex[:6]}"
    base_username = username
    counter = 2
    while row("SELECT id FROM users WHERE lower(username) = lower(?)", (username,)):
        username = f"{base_username}{counter}"
        counter += 1
    password = password or generate_temp_password()
    password_hash, password_salt = hash_password(password)
    user_id = new_id("user")
    execute(
        """
        INSERT INTO users (
          id, company_id, first_name, last_name, username, email,
          password_hash, password_salt, must_change_password, phone, whatsapp, role
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            company_id,
            first_name.strip(),
            last_name.strip(),
            username,
            email.strip().lower(),
            password_hash,
            password_salt,
            1,
            phone,
            whatsapp,
            normalized_role,
        ),
    )
    registration_email = email_new_user_registration(user_id, password)
    email_result = registration_email["email_result"]
    notify("USER_CREATED", f"Super Admin created {normalized_role.replace('_', ' ').title()} user {email}.", user_id, company_id)
    if email_result.get("sent"):
        notify("CREDENTIALS_EMAILED", f"Login credentials emailed to {email}.", user_id, company_id)
    audit("CREATE_SYSTEM_USER", "user", user_id, normalized_role, company_id=company_id)
    user = row(
        """
        SELECT u.id, u.company_id, c.name AS company_name, u.first_name, u.last_name,
               u.username, u.email, u.phone, u.whatsapp, u.role, u.status,
               u.must_change_password, u.created_at
        FROM users u
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE u.id = ?
        """,
        (user_id,),
    ) or {}
    user["temp_password"] = registration_email["temp_password"]
    user["must_change_password"] = bool(user.get("must_change_password"))
    user["email_result"] = email_result
    return user


def update_system_user(
    user_id: str,
    company_id: str,
    first_name: str,
    last_name: str,
    email: str,
    role: str,
    phone: str = "",
    username: str = "",
) -> dict:
    existing = get_system_user(user_id)
    if not existing:
        raise ValueError("Select a valid user to update.")
    if not first_name or not last_name or not email:
        raise ValueError("First name, last name, and email are required.")
    if row("SELECT id FROM companies WHERE id = ?", (company_id,)) is None:
        raise ValueError("Select a valid company for this user.")
    normalized_role = normalize_role(role)
    if normalized_role not in {"SUPER_ADMIN", "ADMIN", "OPERATIONS", "COMPANY_ADMIN", "DECLARANT"}:
        raise ValueError("Role must be Super Admin, Admin Support, Operations, Company Admin, or Declarant.")
    conflict = row("SELECT id FROM users WHERE lower(email) = lower(?) AND id != ?", (email, user_id))
    if conflict:
        raise ValueError("Another user already uses that email.")
    username = (username or existing.get("username") or "").strip().lower()
    if not username:
        username = re.sub(r"[^a-z0-9]+", ".", email.lower().split("@", 1)[0]).strip(".")
    username_conflict = row("SELECT id FROM users WHERE lower(username) = lower(?) AND id != ?", (username, user_id))
    if username_conflict:
        raise ValueError("Another user already uses that username.")
    execute(
        """
        UPDATE users
        SET company_id = ?, first_name = ?, last_name = ?, username = ?,
            email = ?, phone = ?, role = ?
        WHERE id = ?
        """,
        (
            company_id,
            first_name.strip(),
            last_name.strip(),
            username,
            email.strip().lower(),
            phone,
            normalized_role,
            user_id,
        ),
    )
    notify("USER_UPDATED", f"Super Admin updated user {email}.", user_id, company_id)
    audit("UPDATE_SYSTEM_USER", "user", user_id, normalized_role, company_id=company_id)
    return get_system_user(user_id)


def set_system_user_status(user_id: str, status: str) -> dict:
    existing = get_system_user(user_id)
    if not existing:
        raise ValueError("Select a valid user to update.")
    status = "SUSPENDED" if status == "SUSPENDED" else "ACTIVE"
    if existing.get("role") == "SUPER_ADMIN" and status == "SUSPENDED":
        active_super_admins = rows(
            "SELECT id FROM users WHERE role = 'SUPER_ADMIN' AND status = 'ACTIVE' AND id != ?",
            (user_id,),
        )
        if not active_super_admins:
            raise ValueError("You cannot suspend the last active Super Admin.")
    if existing.get("role") == "COMPANY_ADMIN" and status == "SUSPENDED":
        active_company_admins = rows(
            """
            SELECT id FROM users
            WHERE company_id = ? AND role = 'COMPANY_ADMIN' AND status = 'ACTIVE' AND id != ?
            """,
            (existing["company_id"], user_id),
        )
        if not active_company_admins:
            raise ValueError("You cannot suspend the last active Company Admin for this company.")
    execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
    verb = "suspended" if status == "SUSPENDED" else "activated"
    notify("USER_STATUS_CHANGED", f"Super Admin {verb} user {existing.get('email')}.", user_id, existing["company_id"])
    audit("SET_SYSTEM_USER_STATUS", "user", user_id, status, company_id=existing["company_id"])
    return get_system_user(user_id)


def delete_system_user(user_id: str) -> None:
    existing = get_system_user(user_id)
    if not existing:
        raise ValueError("Select a valid user to delete.")
    if existing.get("role") == "SUPER_ADMIN":
        other_super_admins = rows("SELECT id FROM users WHERE role = 'SUPER_ADMIN' AND id != ?", (user_id,))
        if not other_super_admins:
            raise ValueError("You cannot delete the last Super Admin.")
    if existing.get("role") == "COMPANY_ADMIN":
        other_company_admins = rows(
            "SELECT id FROM users WHERE company_id = ? AND role = 'COMPANY_ADMIN' AND id != ?",
            (existing["company_id"], user_id),
        )
        if not other_company_admins:
            raise ValueError("You cannot delete the last Company Admin for this company.")
    execute("DELETE FROM users WHERE id = ?", (user_id,))
    notify("USER_DELETED", f"Super Admin deleted user {existing.get('email')}.", user_id, existing["company_id"])
    audit("DELETE_SYSTEM_USER", "user", user_id, company_id=existing["company_id"])


def create_onboarding(payload: dict, documents: list[dict] | None = None) -> dict:
    username = (payload.get("username") or payload.get("email") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        raise ValueError("Username and password are required.")
    if row("SELECT id FROM users WHERE lower(username) = lower(?) OR lower(email) = lower(?)", (username, payload.get("email"))):
        raise ValueError("A user with that username or email already exists.")
    company_id = new_id("company")
    user_id = new_id("user")
    ref = f"ZCAM-{uuid.uuid4().hex[:8].upper()}"
    docs = documents or []
    password_hash, password_salt = hash_password(password)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO companies (
              id, name, pacra_number, tpin, zra_licence, zaffa_number,
              year_established, employee_count, company_email, phone, whatsapp,
              address_line1, address_line2, city, province, postal_address,
              bank_name, account_number, account_holder, branch, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                payload.get("company_name"),
                payload.get("pacra_number"),
                payload.get("tpin"),
                payload.get("zra_licence"),
                payload.get("zaffa_number"),
                payload.get("year_established"),
                payload.get("employee_count"),
                payload.get("company_email"),
                payload.get("phone"),
                payload.get("whatsapp"),
                payload.get("address_line1"),
                payload.get("address_line2"),
                payload.get("city"),
                payload.get("province"),
                payload.get("postal_address"),
                payload.get("bank_name"),
                payload.get("account_number"),
                payload.get("account_holder"),
                payload.get("branch"),
                "PENDING_APPROVAL",
            ),
        )
        conn.execute(
            """
            INSERT INTO users (
              id, company_id, first_name, last_name, username, email,
              password_hash, password_salt, phone, whatsapp, role
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                company_id,
                payload.get("first_name"),
                payload.get("last_name"),
                username,
                payload.get("email"),
                password_hash,
                password_salt,
                payload.get("phone"),
                payload.get("whatsapp"),
                "COMPANY_ADMIN",
            ),
        )
        for doc in docs:
            file_name = doc.get("file_name") or doc.get("name") or "document"
            file_url = store_uploaded_document(company_id, file_name, doc.get("contents"))
            conn.execute(
                """
                INSERT INTO certificates (id, company_id, name, file_name, file_url, uploaded_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (new_id("cert"), company_id, doc.get("name"), file_name, file_url, user_id),
            )
        conn.execute(
            """
            INSERT INTO notifications (id, company_id, user_id, event_type, message, related_entity_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("notif"),
                company_id,
                user_id,
                "ONBOARDING_SUBMITTED",
                f"Registration {ref} submitted and pending ZAFFA review.",
                company_id,
            ),
        )
        conn.commit()
    return {"company_id": company_id, "user_id": user_id, "reference": ref, "username": username}


def company_admin_user(company_id: str) -> dict | None:
    return row(
        """
        SELECT * FROM users
        WHERE company_id = ? AND role = 'COMPANY_ADMIN'
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (company_id,),
    )


def generate_temp_password() -> str:
    return f"ZCAMS-{secrets.token_urlsafe(8)}"


def registration_login_url(user_id: str | None, email: str | None = None, source: str = "registration") -> str:
    base = os.getenv("PUBLIC_APP_URL", "http://127.0.0.1:8050").rstrip("/")
    params = {"zcams_source": source}
    if user_id:
        params["user"] = user_id
    if email:
        params["email"] = email
    return f"{base}/login?{urlencode(params)}"


def email_new_user_registration(user_id: str, temp_password: str | None = None, source: str = "new-user") -> dict:
    user = row(
        """
        SELECT u.id, u.company_id, c.name AS company_name, u.first_name, u.last_name,
               u.username, u.email, u.role
        FROM users u
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE u.id = ?
        """,
        (user_id,),
    )
    if not user:
        raise ValueError("User not found.")
    password = temp_password or generate_temp_password()
    if temp_password is None:
        password_hash, password_salt = hash_password(password)
        execute(
            """
            UPDATE users
            SET password_hash = ?, password_salt = ?, must_change_password = 1
            WHERE id = ?
            """,
            (password_hash, password_salt, user_id),
        )
    company_name = user.get("company_name") or "Your company"
    contact_name = f"{user.get('first_name') or ''} {user.get('last_name') or ''}".strip() or user.get("email")
    login_url = registration_login_url(user_id, user.get("email"), source)
    subject, text, html = new_user_registration_email(
        company_name=company_name,
        contact_name=contact_name,
        to_email=user["email"],
        role_label=normalize_role(user.get("role")).replace("_", " ").title(),
        username=user.get("username") or user["email"],
        password=password,
        login_url=login_url,
    )
    email_result = send_new_user_registration_email(
        user["email"],
        subject,
        text,
        html=html,
        recipient_name=contact_name,
        description=f"ZCAMS new user registration - {company_name}",
    )
    if email_result.get("sent"):
        notify("CREDENTIALS_EMAILED", f"Login credentials emailed to {user['email']}.", user_id, user["company_id"])
    return {"email_result": email_result, "temp_password": password}


def resend_user_credentials(user_id: str, *, source: str = "credential-resend", actor_role: str = "ADMIN") -> dict:
    user = row(
        """
        SELECT id, company_id, email, role, status
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )
    if not user:
        raise ValueError("User not found.")
    if user.get("status") == "DELETED":
        raise ValueError("Cannot resend credentials to a deleted user.")
    delivery = email_new_user_registration(user_id, source=source)
    email_result = delivery.get("email_result") or {}
    if email_result.get("sent"):
        notify("CREDENTIALS_RESENT", f"Login credentials resent to {user.get('email')}.", user_id, user.get("company_id"))
    audit("RESEND_USER_CREDENTIALS", "user", user_id, normalize_role(actor_role), company_id=user.get("company_id"))
    return {
        "user": user,
        "email_result": email_result,
        "temp_password": delivery.get("temp_password"),
    }


def approve_company(company_id: str, registration_source: str = "onboarding-approval") -> dict:
    company = get_company(company_id)
    if not company:
        raise ValueError(f"Unknown company id: {company_id}")
    admin_user = company_admin_user(company_id)
    if not admin_user:
        raise ValueError("No company admin user found for this CFA registration.")

    temp_password = generate_temp_password()
    password_hash, password_salt = hash_password(temp_password)
    execute(
        "UPDATE companies SET status = 'APPROVED', approved_at = ? WHERE id = ?",
        (now_iso(), company_id),
    )
    execute(
        """
        UPDATE users
        SET password_hash = ?, password_salt = ?, must_change_password = 1
        WHERE id = ?
        """,
        (password_hash, password_salt, admin_user["id"]),
    )

    login_url = registration_login_url(admin_user["id"], admin_user.get("email"), registration_source)
    contact_name = f"{admin_user.get('first_name', '')} {admin_user.get('last_name', '')}".strip() or "CFA Administrator"
    subject, text, html = onboarding_approval_email(
        company_name=company.get("name") or "Your company",
        contact_name=contact_name,
        to_email=admin_user["email"],
        username=admin_user.get("username") or admin_user["email"],
        password=temp_password,
        login_url=login_url,
    )
    email_result = send_new_user_registration_email(
        admin_user["email"],
        subject,
        text,
        html=html,
        recipient_name=contact_name,
        description=f"ZCAMS CFA approval — {company.get('name')}",
    )

    notify("COMPANY_APPROVED", f"{company.get('name')} approved for ZCAMS access.", company_id, company_id)
    if email_result.get("sent"):
        notify(
            "CREDENTIALS_EMAILED",
            f"Login credentials emailed to {admin_user['email']} for {company.get('name')}.",
            company_id,
            company_id,
        )
    audit("APPROVE_COMPANY", "company", company_id)
    return {
        "company": company,
        "user": admin_user,
        "email": email_result,
        "credentials_sent": bool(email_result.get("sent")),
    }


def dashboard_stats(company_id: str | None = None) -> dict:
    """Platform-wide stats when company_id is None; tenant-scoped when provided."""
    if company_id:
        return {
            "companies": 1,
            "bls": row("SELECT COUNT(*) AS count FROM bills_of_lading WHERE company_id = ?", (company_id,))["count"],
            "reviewed": row(
                """
                SELECT COUNT(*) AS count FROM reviewed_bls rb
                JOIN bills_of_lading bl ON bl.id = rb.bl_id
                WHERE bl.company_id = ?
                """,
                (company_id,),
            )["count"],
            "active_zsads": row(
                """
                SELECT COUNT(*) AS count FROM z_sads zs
                JOIN bills_of_lading bl ON bl.id = zs.bl_id
                WHERE zs.is_active = 1 AND bl.company_id = ?
                """,
                (company_id,),
            )["count"],
            "outstanding_invoices": row(
                """
                SELECT COUNT(*) AS count FROM invoices inv
                JOIN reviewed_bls rb ON rb.id = inv.reviewed_bl_id
                JOIN bills_of_lading bl ON bl.id = rb.bl_id
                WHERE inv.status != 'SETTLED' AND bl.company_id = ?
                """,
                (company_id,),
            )["count"],
            "settled_payments": row(
                """
                SELECT COUNT(*) AS count FROM payments pay
                JOIN invoices inv ON inv.id = pay.invoice_id
                JOIN reviewed_bls rb ON rb.id = inv.reviewed_bl_id
                JOIN bills_of_lading bl ON bl.id = rb.bl_id
                WHERE pay.status = 'SETTLED' AND bl.company_id = ?
                """,
                (company_id,),
            )["count"],
            **nav_counts(company_id),
        }
    return {
        "companies": row("SELECT COUNT(*) AS count FROM companies")["count"],
        "bls": row("SELECT COUNT(*) AS count FROM bills_of_lading")["count"],
        "reviewed": row("SELECT COUNT(*) AS count FROM reviewed_bls")["count"],
        "active_zsads": row("SELECT COUNT(*) AS count FROM z_sads WHERE is_active = 1")["count"],
        "outstanding_invoices": row("SELECT COUNT(*) AS count FROM invoices WHERE status != 'SETTLED'")["count"],
        "settled_payments": row("SELECT COUNT(*) AS count FROM payments WHERE status = 'SETTLED'")["count"],
        **nav_counts(),
    }


def admin_dashboard_summary(company_id: str = DEMO_COMPANY_ID) -> dict:
    """Company Admin command-centre counters and readiness signals."""
    stats = dashboard_stats(company_id)
    users = list_company_users(company_id)
    certificates = list_certificates(company_id)
    company = get_company(company_id)
    required_fields = [
        ("pacra_number", "PACRA"),
        ("tpin", "TPIN"),
        ("zra_licence", "ZRA Licence"),
        ("company_email", "Company Email"),
        ("phone", "Phone"),
        ("bank_name", "Bank Name"),
        ("account_number", "Account Number"),
        ("account_holder", "Account Holder"),
    ]
    missing_fields = [label for field, label in required_fields if not company.get(field)]
    active_users = sum(1 for user in users if user.get("status") == "ACTIVE")
    suspended_users = sum(1 for user in users if user.get("status") == "SUSPENDED")
    company_admins = sum(1 for user in users if user.get("role") == "COMPANY_ADMIN")
    declarants = sum(1 for user in users if user.get("role") == "DECLARANT")
    open_tickets = row(
        "SELECT COUNT(*) AS count FROM support_tickets WHERE company_id = ? AND status != 'Resolved'",
        (company_id,),
    )["count"]
    signed_contracts = row(
        "SELECT COUNT(*) AS count FROM contracts WHERE company_id = ? AND status = 'SIGNED'",
        (company_id,),
    )["count"]
    draft_contracts = count_unedited_contracts(company_id)
    return {
        **stats,
        "company_name": company.get("name") or company_id,
        "company_status": company.get("status") or "-",
        "compliance_score": compliance_score(company_id),
        "certificates": len(certificates),
        "missing_fields": missing_fields,
        "banking_ready": all(company.get(field) for field in ("bank_name", "account_number", "account_holder")),
        "active_users": active_users,
        "suspended_users": suspended_users,
        "company_admins": company_admins,
        "declarants": declarants,
        "open_tickets": open_tickets,
        "signed_contracts": signed_contracts,
        "draft_contracts": draft_contracts,
    }


def admin_workflow_rows(company_id: str = DEMO_COMPANY_ID, limit: int = 50) -> list[dict]:
    return rows(
        """
        SELECT
          bl.id AS bl_id,
          bl.bl_number,
          bl.status AS bl_status,
          bl.uploaded_at,
          bl.consignee_name,
          rb.id AS reviewed_id,
          rb.status AS reviewed_status,
          rb.reviewed_at,
          zs.z_sad_number,
          inv.invoice_number,
          inv.status AS invoice_status,
          inv.total,
          pay.status AS payment_status,
          pay.settled_at
        FROM bills_of_lading bl
        LEFT JOIN reviewed_bls rb ON rb.bl_id = bl.id
        LEFT JOIN z_sads zs ON zs.id = rb.z_sad_id
        LEFT JOIN invoices inv ON inv.reviewed_bl_id = rb.id
        LEFT JOIN payments pay ON pay.invoice_id = inv.id
        WHERE bl.company_id = ?
        ORDER BY bl.uploaded_at DESC
        LIMIT ?
        """,
        (company_id, limit),
    )


def admin_contract_rows(company_id: str = DEMO_COMPANY_ID, limit: int = 25) -> list[dict]:
    return rows(
        """
        SELECT id, contract_no, importer_name, importer_email, status, created_at, signed_at
        FROM contracts
        WHERE company_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (company_id, limit),
    )


def admin_recent_audit_rows(company_id: str = DEMO_COMPANY_ID, limit: int = 20) -> list[dict]:
    return rows(
        """
        SELECT a.*, u.first_name, u.last_name, u.email AS actor_email
        FROM audit_events a
        LEFT JOIN users u ON u.id = a.user_id
        WHERE a.company_id = ? OR a.company_id IS NULL
        ORDER BY a.created_at DESC
        LIMIT ?
        """,
        (company_id, limit),
    )


def admin_support_summary() -> dict:
    """Platform support counters for the Admin Support Centre."""
    stats = dashboard_stats()
    open_tickets = row("SELECT COUNT(*) AS count FROM support_tickets WHERE status != 'Resolved'")["count"]
    failed_logins = row("SELECT COUNT(*) AS count FROM login_events WHERE success = 0")["count"]
    active_sessions = row(
        """
        SELECT COUNT(*) AS count
        FROM user_sessions
        WHERE revoked_at IS NULL AND datetime(expires_at) > datetime('now')
        """
    )["count"]
    pending_bls = row("SELECT COUNT(*) AS count FROM bills_of_lading WHERE status = 'UPLOADED'")["count"]
    return {
        **stats,
        "open_tickets": open_tickets,
        "failed_logins": failed_logins,
        "active_sessions": active_sessions,
        "pending_bls": pending_bls,
    }


def admin_support_company_readiness_rows(limit: int = 100) -> list[dict]:
    """Cross-CFA readiness view for support staff."""
    companies = rows(
        """
        SELECT c.*,
               COUNT(DISTINCT u.id) AS users_count,
               SUM(CASE WHEN u.role = 'COMPANY_ADMIN' THEN 1 ELSE 0 END) AS company_admins,
               SUM(CASE WHEN u.role = 'DECLARANT' THEN 1 ELSE 0 END) AS declarants,
               COUNT(DISTINCT cert.id) AS certificates,
               COUNT(DISTINCT st.id) AS open_tickets
        FROM companies c
        LEFT JOIN users u ON u.company_id = c.id
        LEFT JOIN certificates cert ON cert.company_id = c.id
        LEFT JOIN support_tickets st ON st.company_id = c.id AND st.status != 'Resolved'
        GROUP BY c.id
        ORDER BY c.created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    required_fields = [
        ("pacra_number", "PACRA"),
        ("tpin", "TPIN"),
        ("zra_licence", "ZRA Licence"),
        ("company_email", "Company Email"),
        ("phone", "Phone"),
        ("bank_name", "Bank Name"),
        ("account_number", "Account Number"),
        ("account_holder", "Account Holder"),
    ]
    readiness = []
    for company in companies:
        missing = [label for field, label in required_fields if not company.get(field)]
        readiness.append(
            {
                "company_id": company.get("id"),
                "company_name": company.get("name") or "-",
                "status": company.get("status") or "-",
                "compliance_score": compliance_score(company["id"]),
                "banking_ready": "Yes" if all(company.get(field) for field in ("bank_name", "account_number", "account_holder")) else "No",
                "users": int(company.get("users_count") or 0),
                "company_admins": int(company.get("company_admins") or 0),
                "declarants": int(company.get("declarants") or 0),
                "certificates": int(company.get("certificates") or 0),
                "open_tickets": int(company.get("open_tickets") or 0),
                "missing_fields": ", ".join(missing) if missing else "None",
                "created_at": company.get("created_at") or "-",
            }
        )
    return readiness


def nav_counts(company_id: str | None = None) -> dict:
    """Counts for sidebar badges and dashboard shortcuts."""
    if company_id:
        return {
            "bls_pending": row(
                "SELECT COUNT(*) AS count FROM bills_of_lading WHERE status = 'UPLOADED' AND company_id = ?",
                (company_id,),
            )["count"],
            "reviewed_invoice_ready": row(
                """
                SELECT COUNT(*) AS count FROM reviewed_bls rb
                JOIN bills_of_lading bl ON bl.id = rb.bl_id
                WHERE bl.company_id = ? AND rb.status IN ('REVIEWED_ZSAD_ISSUED', 'AWAITING_PAYMENT')
                """,
                (company_id,),
            )["count"],
            "outstanding_invoices": row(
                """
                SELECT COUNT(*) AS count FROM invoices inv
                JOIN reviewed_bls rb ON rb.id = inv.reviewed_bl_id
                JOIN bills_of_lading bl ON bl.id = rb.bl_id
                WHERE inv.status != 'SETTLED' AND bl.company_id = ?
                """,
                (company_id,),
            )["count"],
            "checkout_pending": row(
                """
                SELECT COUNT(*) AS count FROM invoices inv
                JOIN reviewed_bls rb ON rb.id = inv.reviewed_bl_id
                JOIN bills_of_lading bl ON bl.id = rb.bl_id
                WHERE inv.status = 'AWAITING_PAYMENT' AND bl.company_id = ?
                """,
                (company_id,),
            )["count"],
            "release_pending": row(
                """
                SELECT COUNT(*) AS count FROM reviewed_bls rb
                JOIN bills_of_lading bl ON bl.id = rb.bl_id
                WHERE bl.company_id = ? AND rb.status = 'SETTLED_RELEASE_PENDING'
                """,
                (company_id,),
            )["count"],
            "pending_companies": 0,
            "notifications_unread": row(
                "SELECT COUNT(*) AS count FROM notifications WHERE is_read = 0 AND company_id = ?",
                (company_id,),
            )["count"],
        }
    return {
        "bls_pending": row("SELECT COUNT(*) AS count FROM bills_of_lading WHERE status = 'UPLOADED'")["count"],
        "reviewed_invoice_ready": row(
            """
            SELECT COUNT(*) AS count FROM reviewed_bls
            WHERE status IN ('REVIEWED_ZSAD_ISSUED', 'AWAITING_PAYMENT')
            """
        )["count"],
        "outstanding_invoices": row("SELECT COUNT(*) AS count FROM invoices WHERE status != 'SETTLED'")["count"],
        "checkout_pending": row(
            "SELECT COUNT(*) AS count FROM invoices WHERE status = 'AWAITING_PAYMENT'"
        )["count"],
        "release_pending": row(
            "SELECT COUNT(*) AS count FROM reviewed_bls WHERE status = 'SETTLED_RELEASE_PENDING'"
        )["count"],
        "pending_companies": row(
            "SELECT COUNT(*) AS count FROM companies WHERE status = 'PENDING_APPROVAL'"
        )["count"],
        "notifications_unread": row(
            "SELECT COUNT(*) AS count FROM notifications WHERE is_read = 0"
        )["count"],
    }


def workflow_journey_counts() -> dict:
    """Progress counters for the visible customs journey strip."""
    return {
        "bl_uploaded": row("SELECT COUNT(*) AS count FROM bills_of_lading")["count"],
        "zsad_issued": row("SELECT COUNT(*) AS count FROM z_sads WHERE is_active = 1")["count"],
        "invoice_generated": row("SELECT COUNT(*) AS count FROM invoices WHERE status != 'CANCELLED'")["count"],
        "payment_cleared": row("SELECT COUNT(*) AS count FROM payments WHERE status = 'SETTLED'")["count"],
        "cargo_released": row("SELECT COUNT(*) AS count FROM reviewed_bls WHERE status = 'CARGO_RELEASED'")["count"],
    }


def display_bl_number(bl: dict) -> str:
    number = bl.get("bl_number") or ""
    if BL_CANCELLED_SUFFIX in number:
        return number.split(BL_CANCELLED_SUFFIX, 1)[0]
    return number


def get_user_display(user_id: str | None) -> str:
    if not user_id:
        return "Unknown user"
    user = row("SELECT first_name, last_name, email FROM users WHERE id = ?", (user_id,))
    if not user:
        return user_id
    name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    return name or user.get("email") or user_id


def find_bl_number_conflict(bl_number: str, company_id: str = DEMO_COMPANY_ID) -> dict | None:
    """Active BL for this company with the same number (excludes cancelled records)."""
    return row(
        """
        SELECT bl.*,
               rb.id AS reviewed_id,
               rb.status AS reviewed_status,
               zs.z_sad_number,
               zs.id AS z_sad_id
        FROM bills_of_lading bl
        LEFT JOIN reviewed_bls rb ON rb.bl_id = bl.id AND rb.status != 'CANCELLED'
        LEFT JOIN z_sads zs ON zs.id = rb.z_sad_id AND zs.is_active = 1
        WHERE bl.bl_number = ? AND bl.company_id = ? AND bl.status != 'CANCELLED'
        """,
        (bl_number, company_id),
    )


class BlNumberConflict(ValueError):
    """Same company already has this BL with an issued Z-SAD."""

    def __init__(self, conflict: dict):
        self.conflict = conflict
        zsad = conflict.get("z_sad_number") or "a Z-SAD"
        super().__init__(
            f"Duplicate BL number: {display_bl_number(conflict)}. "
            f"Z-SAD {zsad} was already generated for your company. "
            "Detach the Z-SAD from the previous record to cancel it and re-use this BL number."
        )


def cancel_bl_for_reupload(
    bl_id: str,
    reason: str,
    *,
    reason_detail: str | None = None,
    cancelled_by: str = DEMO_USER_ID,
    company_id: str = DEMO_COMPANY_ID,
) -> dict:
    """Cancel an existing BL journey so the BL number can be uploaded again."""
    if reason not in BL_CANCEL_REASONS:
        raise ValueError(f"Invalid cancel reason. Choose one of: {', '.join(BL_CANCEL_REASONS)}")
    if reason == "Other" and not (reason_detail or "").strip():
        raise ValueError("Please state the reason when selecting Other.")

    bl = row(
        "SELECT * FROM bills_of_lading WHERE id = ? AND company_id = ? AND status != 'CANCELLED'",
        (bl_id, company_id),
    )
    if not bl:
        raise ValueError("BL record not found or already cancelled.")

    reviewed = row("SELECT * FROM reviewed_bls WHERE bl_id = ? AND status != 'CANCELLED'", (bl_id,))
    if reviewed and (reviewed.get("status") or "") in {"SETTLED", "SETTLED_RELEASE_PENDING", "CARGO_RELEASED"}:
        raise ValueError("Cannot cancel this BL after payment settlement or cargo release.")

    cancelled_at = now_iso()
    archived_number = f"{bl['bl_number']}{BL_CANCELLED_SUFFIX}{bl_id}"

    with connect() as conn:
        if reviewed:
            reviewed_id = reviewed["id"]
            open_invoices = conn.execute(
                "SELECT id FROM invoices WHERE reviewed_bl_id = ? AND status != 'CANCELLED'",
                (reviewed_id,),
            ).fetchall()
            if open_invoices:
                conn.execute(
                    """
                    UPDATE payments SET status = 'CANCELLED'
                    WHERE invoice_id IN (
                      SELECT id FROM invoices WHERE reviewed_bl_id = ? AND status != 'CANCELLED'
                    )
                    """,
                    (reviewed_id,),
                )
                conn.execute(
                    "UPDATE invoices SET status = 'CANCELLED' WHERE reviewed_bl_id = ? AND status != 'CANCELLED'",
                    (reviewed_id,),
                )
            conn.execute(
                "UPDATE z_sads SET is_active = 0, deactivated_at = ? WHERE reviewed_bl_id = ? AND is_active = 1",
                (cancelled_at, reviewed_id),
            )
            conn.execute(
                "UPDATE reviewed_bls SET status = 'CANCELLED' WHERE id = ?",
                (reviewed_id,),
            )
        conn.execute(
            """
            UPDATE bills_of_lading
            SET status = 'CANCELLED',
                bl_number = ?,
                cancelled_at = ?,
                cancelled_by = ?,
                cancel_reason = ?,
                cancel_reason_detail = ?
            WHERE id = ?
            """,
            (
                archived_number,
                cancelled_at,
                cancelled_by,
                reason,
                (reason_detail or "").strip() or None,
                bl_id,
            ),
        )
        conn.commit()

    notify(
        "BL_CANCELLED",
        f"BL {display_bl_number(bl)} cancelled ({reason}). The BL number can be uploaded again.",
        bl_id,
        company_id=company_id,
    )
    audit(
        "CANCEL_BL",
        "bill_of_lading",
        bl_id,
        details=f"{reason}: {reason_detail or ''}".strip(),
        company_id=company_id,
    )
    return get_bl(bl_id)


def create_bl(
    payload: dict,
    auto_review: bool = False,
    use_ocr_defaults: bool = True,
    company_id: str = DEMO_COMPANY_ID,
) -> dict:
    conflict = find_bl_number_conflict(payload["bl_number"], company_id)
    if conflict:
        if conflict.get("z_sad_number") or conflict.get("reviewed_status") in {
            "REVIEWED_ZSAD_ISSUED",
            "AWAITING_PAYMENT",
            "SETTLED",
            "SETTLED_RELEASE_PENDING",
            "CLEARED",
        }:
            raise BlNumberConflict(conflict)
        raise ValueError(f"Duplicate BL number: {payload['bl_number']}")
    extraction = extract_bl_fields(payload.get("file_path")) if use_ocr_defaults else {}
    data = {**extraction, **payload}
    bl_id = new_id("bl")
    cargo_id = new_id("cargo")
    category = data.get("gn83_category", "MOTOR_VEHICLE")
    units = billable_units(
        category,
        no_containers=data.get("no_containers"),
        gross_weight=data.get("gross_weight"),
        quantity=data.get("quantity", 1),
    )
    min_fee = lookup_fee(
        data.get("route_type", "Import"),
        data.get("transport_mode", "Sea"),
        category,
        quantity=units,
        no_containers=data.get("no_containers"),
        gross_weight=data.get("gross_weight"),
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO bills_of_lading (
              id, company_id, bl_number, doc_type, route_type, transport_mode,
              zra_regime, bl_type, currency, agent_license, company_name,
              consignor_tin, declarant_number, consignment_value,
              shipper_name, shipper_address, shipper_country,
              carrier_name, vessel_vehicle_no, origin, destination,
              consignee_tin, consignee_name, gross_weight, no_containers,
              gn83_unit, gn83_fee_usd, file_name, status, uploaded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bl_id,
                company_id,
                data.get("bl_number"),
                data.get("doc_type"),
                data.get("route_type"),
                data.get("transport_mode"),
                data.get("zra_regime"),
                data.get("bl_type"),
                data.get("currency"),
                data.get("agent_license") or data.get("agentLicense"),
                data.get("company_name"),
                data.get("consignor_tin"),
                data.get("declarant_number"),
                data.get("consignment_value"),
                data.get("shipper_name"),
                data.get("shipper_address"),
                data.get("shipper_country"),
                data.get("carrier_name"),
                data.get("vessel_vehicle_no"),
                data.get("origin"),
                data.get("destination"),
                data.get("consignee_tin"),
                data.get("consignee_name"),
                data.get("gross_weight", 0),
                data.get("no_containers", 0),
                data.get("gn83_unit"),
                data.get("gn83_fee_usd", min_fee),
                data.get("file_name", "demo-bl.pdf"),
                "UPLOADED",
                DEMO_USER_ID,
            ),
        )
        conn.execute(
            """
            INSERT INTO cargo_items (
              id, bl_id, description, hs_code, quantity, unit, weight,
              transport_mode, gn83_category, min_fee_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cargo_id,
                bl_id,
                data.get("cargo_description", data.get("description", "General cargo")),
                data.get("hs_code"),
                units,
                data.get("unit", "Unit"),
                data.get("gross_weight", 0),
                data.get("transport_mode", "Sea"),
                data.get("gn83_category", "MOTOR_VEHICLE"),
                min_fee,
            ),
        )
        conn.commit()
    notify("BL_UPLOADED", f"BL {data.get('bl_number')} uploaded by Admin ZCAMS.", bl_id)
    audit("UPLOAD_BL", "bill_of_lading", bl_id)
    bl = get_bl(bl_id)
    if auto_review:
        bl["reviewed_bl"] = review_bl(bl_id)
    return bl


def update_bl(bl_id: str, payload: dict, *, company_id: str = DEMO_COMPANY_ID, actor_id: str | None = None) -> dict:
    existing = get_bl(bl_id)
    if not existing or existing.get("company_id") != company_id:
        raise ValueError("BL record was not found for this company.")
    if existing.get("status") != "UPLOADED":
        raise ValueError("Only saved BLs that have not been reviewed or issued a Z-SAD can be amended.")

    new_bl_number = str(payload.get("bl_number") or "").strip()
    if not new_bl_number:
        raise ValueError("BL number is required.")
    duplicate = row(
        """
        SELECT id
        FROM bills_of_lading
        WHERE bl_number = ? AND company_id = ? AND id != ? AND status != 'CANCELLED'
        """,
        (new_bl_number, company_id, bl_id),
    )
    if duplicate:
        raise ValueError(f"Duplicate BL number: {new_bl_number}")

    category = payload.get("gn83_category", "MOTOR_VEHICLE")
    units = billable_units(
        category,
        no_containers=payload.get("no_containers"),
        gross_weight=payload.get("gross_weight"),
        quantity=payload.get("quantity", 1),
    )
    min_fee = lookup_fee(
        payload.get("route_type", "Import"),
        payload.get("transport_mode", "Sea"),
        category,
        quantity=units,
        no_containers=payload.get("no_containers"),
        gross_weight=payload.get("gross_weight"),
    )
    file_name = payload.get("file_name") or existing.get("file_name") or "demo-bl.pdf"

    with connect() as conn:
        conn.execute(
            """
            UPDATE bills_of_lading
            SET bl_number = ?,
                doc_type = ?,
                route_type = ?,
                transport_mode = ?,
                zra_regime = ?,
                bl_type = ?,
                currency = ?,
                agent_license = ?,
                company_name = ?,
                consignor_tin = ?,
                declarant_number = ?,
                consignment_value = ?,
                origin = ?,
                destination = ?,
                consignee_tin = ?,
                consignee_name = ?,
                gross_weight = ?,
                no_containers = ?,
                gn83_unit = ?,
                gn83_fee_usd = ?,
                file_name = ?
            WHERE id = ? AND company_id = ? AND status = 'UPLOADED'
            """,
            (
                new_bl_number,
                payload.get("doc_type"),
                payload.get("route_type"),
                payload.get("transport_mode"),
                payload.get("zra_regime"),
                payload.get("bl_type"),
                payload.get("currency"),
                payload.get("agent_license") or payload.get("agentLicense"),
                payload.get("company_name"),
                payload.get("consignor_tin"),
                payload.get("declarant_number"),
                payload.get("consignment_value"),
                payload.get("origin"),
                payload.get("destination"),
                payload.get("consignee_tin"),
                payload.get("consignee_name"),
                payload.get("gross_weight", 0),
                payload.get("no_containers", 0),
                payload.get("gn83_unit"),
                payload.get("gn83_fee_usd", min_fee),
                file_name,
                bl_id,
                company_id,
            ),
        )
        conn.execute(
            """
            UPDATE cargo_items
            SET description = ?,
                quantity = ?,
                unit = ?,
                weight = ?,
                transport_mode = ?,
                gn83_category = ?,
                min_fee_usd = ?
            WHERE id = (
                SELECT id FROM cargo_items WHERE bl_id = ? ORDER BY rowid LIMIT 1
            )
            """,
            (
                payload.get("cargo_description", payload.get("description", "General cargo")),
                units,
                payload.get("unit", "Unit"),
                payload.get("gross_weight", 0),
                payload.get("transport_mode", "Sea"),
                category,
                min_fee,
                bl_id,
            ),
        )
        conn.commit()

    notify("BL_AMENDED", f"BL {new_bl_number} amended.", bl_id, company_id)
    audit("AMEND_BL", "bill_of_lading", bl_id, "Saved BL amended", company_id=company_id, user_id=actor_id)
    return get_bl(bl_id)


def correct_reviewed_bl_for_asycuda(
    reviewed_id: str,
    payload: dict,
    *,
    correction_reason: str,
    company_id: str = DEMO_COMPANY_ID,
    actor_id: str | None = None,
) -> dict:
    """Apply an audited ASYCUDA correction to the BL tied to an active Z-SAD."""
    reviewed = get_reviewed_bl(reviewed_id)
    if not reviewed or reviewed.get("company_id") != company_id:
        raise ValueError("Reviewed BL was not found for this company.")
    status = reviewed.get("status") or ""
    if status not in {"REVIEWED_ZSAD_ISSUED", "AWAITING_PAYMENT"}:
        if status == "CARGO_RELEASED":
            raise ValueError("Cannot correct BL after cargo release has been issued.")
        if status == "SETTLED_RELEASE_PENDING":
            raise ValueError("Cannot correct BL after settlement while cargo release is pending.")
        if status == "SETTLED":
            raise ValueError("Cannot correct BL after payment settlement.")
        raise ValueError("ASYCUDA BL correction is only available before settlement.")
    if not reviewed.get("z_sad_id"):
        raise ValueError("No active Z-SAD is linked to this reviewed BL.")
    correction_reason = str(correction_reason or "").strip()
    if not correction_reason:
        raise ValueError("Enter the ASYCUDA correction reason before reissuing the Z-SAD.")

    bl_id = reviewed["bl_id"]
    new_bl_number = str(payload.get("bl_number") or "").strip()
    if not new_bl_number:
        raise ValueError("BL number is required.")
    duplicate = row(
        """
        SELECT id
        FROM bills_of_lading
        WHERE bl_number = ? AND company_id = ? AND id != ? AND status != 'CANCELLED'
        """,
        (new_bl_number, company_id, bl_id),
    )
    if duplicate:
        raise ValueError(f"Duplicate BL number: {new_bl_number}")

    category = payload.get("gn83_category", "MOTOR_VEHICLE")
    units = billable_units(
        category,
        no_containers=payload.get("no_containers"),
        gross_weight=payload.get("gross_weight"),
        quantity=payload.get("quantity", 1),
    )
    min_fee = lookup_fee(
        payload.get("route_type", "Import"),
        payload.get("transport_mode", "Sea"),
        category,
        quantity=units,
        no_containers=payload.get("no_containers"),
        gross_weight=payload.get("gross_weight"),
    )
    zsad_number = reviewed.get("z_sad_number")
    open_invoices = rows(
        "SELECT id, invoice_number FROM invoices WHERE reviewed_bl_id = ? AND status != 'CANCELLED'",
        (reviewed_id,),
    )
    cancelled_numbers = [inv["invoice_number"] for inv in open_invoices]

    with connect() as conn:
        if open_invoices:
            conn.execute(
                """
                UPDATE payments
                SET status = 'CANCELLED'
                WHERE invoice_id IN (
                  SELECT id FROM invoices WHERE reviewed_bl_id = ? AND status != 'CANCELLED'
                )
                """,
                (reviewed_id,),
            )
            conn.execute(
                "UPDATE invoices SET status = 'CANCELLED' WHERE reviewed_bl_id = ? AND status != 'CANCELLED'",
                (reviewed_id,),
            )
        conn.execute(
            """
            UPDATE bills_of_lading
            SET bl_number = ?,
                doc_type = ?,
                route_type = ?,
                transport_mode = ?,
                zra_regime = ?,
                company_name = ?,
                origin = ?,
                destination = ?,
                consignee_tin = ?,
                consignor_tin = ?,
                consignee_name = ?,
                gross_weight = ?,
                no_containers = ?,
                gn83_unit = ?,
                gn83_fee_usd = ?
            WHERE id = ? AND company_id = ?
            """,
            (
                new_bl_number,
                payload.get("doc_type"),
                payload.get("route_type"),
                payload.get("transport_mode"),
                payload.get("zra_regime"),
                payload.get("company_name"),
                payload.get("origin"),
                payload.get("destination"),
                payload.get("consignee_tin"),
                payload.get("consignor_tin"),
                payload.get("consignee_name"),
                payload.get("gross_weight", 0),
                payload.get("no_containers", 0),
                payload.get("gn83_unit"),
                payload.get("gn83_fee_usd", min_fee),
                bl_id,
                company_id,
            ),
        )
        conn.execute(
            """
            UPDATE cargo_items
            SET description = ?,
                quantity = ?,
                unit = ?,
                weight = ?,
                transport_mode = ?,
                gn83_category = ?,
                min_fee_usd = ?
            WHERE id = (
                SELECT id FROM cargo_items WHERE bl_id = ? ORDER BY rowid LIMIT 1
            )
            """,
            (
                payload.get("cargo_description", payload.get("description", "General cargo")),
                units,
                payload.get("gn83_unit") or payload.get("unit", "Unit"),
                payload.get("gross_weight", 0),
                payload.get("transport_mode", "Sea"),
                category,
                min_fee,
                bl_id,
            ),
        )
        conn.execute("UPDATE reviewed_bls SET status = 'REVIEWED_ZSAD_ISSUED' WHERE id = ?", (reviewed_id,))
        conn.execute(
            "UPDATE bills_of_lading SET status = 'REVIEWED_ZSAD_ISSUED', reviewed_at = ? WHERE id = ?",
            (now_iso(), bl_id),
        )
        conn.commit()

    notify(
        "ASYCUDA_BL_CORRECTED",
        f"BL {new_bl_number} corrected after ASYCUDA feedback. Z-SAD {zsad_number} remains active for resend.",
        reviewed_id,
        company_id=company_id,
    )
    if cancelled_numbers:
        notify(
            "INVOICE_CANCELLED_FOR_ASYCUDA_CORRECTION",
            f"{len(cancelled_numbers)} invoice(s) cancelled after ASYCUDA BL correction for {new_bl_number}.",
            reviewed_id,
            company_id=company_id,
        )
    audit(
        "ASYCUDA_BL_CORRECTION",
        "reviewed_bl",
        reviewed_id,
        details=f"{correction_reason} | Z-SAD retained: {zsad_number}",
        company_id=company_id,
        user_id=actor_id,
    )
    updated = get_reviewed_bl(reviewed_id)
    updated["asycuda_correction_summary"] = {
        "zsad_number": zsad_number,
        "cancelled_invoices": cancelled_numbers,
        "cancelled_count": len(cancelled_numbers),
    }
    return updated


def list_bls(company_id: str | None = None) -> list[dict]:
    query = """
        SELECT bl.*,
               u.first_name AS cancelled_by_first,
               u.last_name AS cancelled_by_last,
               u.email AS cancelled_by_email
        FROM bills_of_lading bl
        LEFT JOIN users u ON u.id = bl.cancelled_by
    """
    params: tuple = ()
    if company_id:
        query += " WHERE bl.company_id = ?"
        params = (company_id,)
    query += " ORDER BY bl.uploaded_at DESC"
    bls = rows(query, params)
    for bl in bls:
        bl["display_bl_number"] = display_bl_number(bl)
        if bl.get("cancelled_by_first") or bl.get("cancelled_by_last"):
            bl["cancelled_by_name"] = (
                f"{bl.get('cancelled_by_first', '')} {bl.get('cancelled_by_last', '')}".strip()
            )
        else:
            bl["cancelled_by_name"] = get_user_display(bl.get("cancelled_by"))
    return bls


def get_bl(bl_id: str) -> dict:
    bl = row("SELECT * FROM bills_of_lading WHERE id = ?", (bl_id,)) or {}
    if bl:
        bl["cargo_items"] = rows("SELECT * FROM cargo_items WHERE bl_id = ?", (bl_id,))
    return bl


def generate_zsad_number(bl_number: str) -> str:
    suffix = (bl_number or "XXXX")[-4:].upper().replace(" ", "X")
    digits = random.choices("123456789", k=9)
    letters = random.choices(string.ascii_uppercase, k=6)
    mixed = digits + letters
    random.shuffle(mixed)
    return f"Z-SAD-{suffix}-{''.join(mixed)}"


def review_bl(bl_id: str) -> dict:
    bl = get_bl(bl_id)
    if not bl:
        raise ValueError(f"Unknown BL id: {bl_id}")
    existing = row("SELECT * FROM reviewed_bls WHERE bl_id = ?", (bl_id,))
    if existing:
        return get_reviewed_bl(existing["id"])
    reviewed_id = new_id("rbl")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO reviewed_bls (id, bl_id, status, reviewed_by)
            VALUES (?, ?, ?, ?)
            """,
            (reviewed_id, bl_id, "REVIEWED_ZSAD_ISSUED", DEMO_USER_ID),
        )
        zs_id = new_id("zsad")
        while True:
            number = generate_zsad_number(bl["bl_number"])
            if not conn.execute("SELECT id FROM z_sads WHERE z_sad_number = ?", (number,)).fetchone():
                break
        conn.execute(
            """
            INSERT INTO z_sads (id, reviewed_bl_id, bl_id, z_sad_number)
            VALUES (?, ?, ?, ?)
            """,
            (zs_id, reviewed_id, bl_id, number),
        )
        conn.execute("UPDATE reviewed_bls SET z_sad_id = ? WHERE id = ?", (zs_id, reviewed_id))
        conn.execute(
            "UPDATE bills_of_lading SET status = 'REVIEWED_ZSAD_ISSUED', reviewed_at = ? WHERE id = ?",
            (now_iso(), bl_id),
        )
        conn.commit()
    notify("BL_REVIEWED", f"BL {bl['bl_number']} review completed. Z-SAD {number} issued.", reviewed_id)
    notify("ZSAD_GENERATED", f"Z-SAD {number} generated for BL {bl['bl_number']}. Single use - do not share.", zs_id)
    audit("REVIEW_BL", "reviewed_bl", reviewed_id)
    return get_reviewed_bl(reviewed_id)


def list_reviewed_bls(company_id: str | None = DEMO_COMPANY_ID, include_cancelled: bool = False) -> list[dict]:
    query = """
        SELECT rb.*, bl.bl_number, bl.consignee_name, bl.consignee_tin, bl.route_type,
               bl.transport_mode, bl.no_containers, bl.gross_weight, bl.company_id,
               zs.z_sad_number, zs.is_active, zs.is_used, ci.gn83_category
        FROM reviewed_bls rb
        JOIN bills_of_lading bl ON bl.id = rb.bl_id
        LEFT JOIN z_sads zs ON zs.id = rb.z_sad_id
        LEFT JOIN cargo_items ci ON ci.bl_id = bl.id
    """
    params: tuple[Any, ...] = ()
    filters = []
    if company_id is not None:
        filters.append("bl.company_id = ?")
        params = (company_id,)
    if not include_cancelled:
        filters.append("rb.status != 'CANCELLED'")
        filters.append("bl.status != 'CANCELLED'")
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY rb.reviewed_at DESC"
    reviewed = rows(query, params)
    return reviewed


def get_reviewed_bl(reviewed_id: str) -> dict:
    reviewed = row(
        """
        SELECT rb.*, bl.bl_number, bl.consignee_name, bl.consignee_tin, bl.route_type,
               bl.company_id,
               bl.transport_mode, bl.no_containers, bl.gross_weight, zs.z_sad_number,
               zs.is_active, zs.is_used
        FROM reviewed_bls rb
        JOIN bills_of_lading bl ON bl.id = rb.bl_id
        LEFT JOIN z_sads zs ON zs.id = rb.z_sad_id
        WHERE rb.id = ?
        """,
        (reviewed_id,),
    ) or {}
    if reviewed:
        reviewed["cargo_items"] = rows("SELECT * FROM cargo_items WHERE bl_id = ?", (reviewed["bl_id"],))
    return reviewed


def list_z_sad_history(reviewed_bl_id: str) -> list[dict]:
    history = rows(
        """
        SELECT zs.*,
               (
                 SELECT COUNT(*)
                 FROM invoices inv
                 WHERE inv.z_sad_id = zs.id AND inv.status != 'CANCELLED'
               ) AS open_invoices,
               (
                 SELECT COUNT(*)
                 FROM invoices inv
                 WHERE inv.z_sad_id = zs.id
               ) AS invoice_count
        FROM z_sads zs
        WHERE zs.reviewed_bl_id = ?
        ORDER BY zs.is_active DESC, zs.generated_at DESC, zs.id DESC
        """,
        (reviewed_bl_id,),
    )
    return history


def get_zsad_detach_preview(reviewed_id: str) -> dict:
    reviewed = get_reviewed_bl(reviewed_id)
    if not reviewed:
        raise ValueError(f"Unknown reviewed BL id: {reviewed_id}")
    open_invoices = rows(
        """
        SELECT id, invoice_number, invoice_type, status, total, z_sad_id
        FROM invoices
        WHERE reviewed_bl_id = ? AND status != 'CANCELLED'
        ORDER BY created_at DESC
        """,
        (reviewed_id,),
    )
    status = reviewed.get("status") or ""
    allowed_detach_statuses = {"REVIEWED_ZSAD_ISSUED", "AWAITING_PAYMENT"}
    can_detach = status in allowed_detach_statuses
    block_reason = None
    if status == "CARGO_RELEASED":
        block_reason = "Cargo has already been released for this BL. Z-SAD replacement is not permitted."
    elif status == "SETTLED_RELEASE_PENDING":
        block_reason = "Payment has already settled and cargo release is pending. Z-SAD detachment is not permitted."
    elif status == "SETTLED":
        block_reason = "Payment has already settled for this BL. Z-SAD detachment is not permitted."
    elif not can_detach:
        block_reason = "Z-SAD detachment is only available before settlement, while the BL is awaiting payment or newly reviewed."
    return {
        "reviewed_id": reviewed_id,
        "bl_number": reviewed.get("bl_number"),
        "current_zsad": reviewed.get("z_sad_number"),
        "reviewed_status": status,
        "open_invoices": open_invoices,
        "history": list_z_sad_history(reviewed_id),
        "can_detach": can_detach,
        "block_reason": block_reason,
    }


def detach_zsad(reviewed_id: str, issue_new: bool = True) -> dict:
    """Retire the active Z-SAD, cancel open invoices/payments, and optionally issue a new Z-SAD."""
    reviewed = get_reviewed_bl(reviewed_id)
    if not reviewed:
        raise ValueError(f"Unknown reviewed BL id: {reviewed_id}")
    status = reviewed.get("status") or ""
    if status not in {"REVIEWED_ZSAD_ISSUED", "AWAITING_PAYMENT"}:
        if status == "CARGO_RELEASED":
            raise ValueError("Cannot detach Z-SAD after cargo release has been issued.")
        if status == "SETTLED_RELEASE_PENDING":
            raise ValueError("Cannot detach Z-SAD after settlement while cargo release is pending.")
        if status == "SETTLED":
            raise ValueError("Cannot detach Z-SAD after payment settlement.")
        raise ValueError("Z-SAD detachment is only available before settlement.")
    if not reviewed.get("z_sad_id"):
        raise ValueError("No active Z-SAD is linked to this reviewed BL.")

    old_zsad = reviewed.get("z_sad_number")
    old_zsad_id = reviewed["z_sad_id"]
    open_invoices = rows(
        "SELECT id, invoice_number, status FROM invoices WHERE reviewed_bl_id = ? AND status != 'CANCELLED'",
        (reviewed_id,),
    )
    cancelled_numbers = [inv["invoice_number"] for inv in open_invoices]

    with connect() as conn:
        conn.execute(
            "UPDATE z_sads SET is_active = 0, deactivated_at = ? WHERE id = ?",
            (now_iso(), old_zsad_id),
        )
        if open_invoices:
            conn.execute(
                """
                UPDATE payments
                SET status = 'CANCELLED'
                WHERE invoice_id IN (
                  SELECT id FROM invoices WHERE reviewed_bl_id = ? AND status != 'CANCELLED'
                )
                """,
                (reviewed_id,),
            )
            conn.execute(
                "UPDATE invoices SET status = 'CANCELLED' WHERE reviewed_bl_id = ? AND status != 'CANCELLED'",
                (reviewed_id,),
            )
        new_number = None
        new_zsad_id = None
        if issue_new:
            new_zsad_id = new_id("zsad")
            while True:
                new_number = generate_zsad_number(reviewed["bl_number"])
                if not conn.execute("SELECT id FROM z_sads WHERE z_sad_number = ?", (new_number,)).fetchone():
                    break
            conn.execute(
                "INSERT INTO z_sads (id, reviewed_bl_id, bl_id, z_sad_number) VALUES (?, ?, ?, ?)",
                (new_zsad_id, reviewed_id, reviewed["bl_id"], new_number),
            )
            conn.execute("UPDATE reviewed_bls SET z_sad_id = ?, status = 'REVIEWED_ZSAD_ISSUED' WHERE id = ?", (new_zsad_id, reviewed_id))
        else:
            conn.execute("UPDATE reviewed_bls SET z_sad_id = NULL, status = 'REVIEWED' WHERE id = ?", (reviewed_id,))
        conn.execute(
            "UPDATE bills_of_lading SET status = 'REVIEWED_ZSAD_ISSUED' WHERE id = ?",
            (reviewed["bl_id"],),
        )
        conn.commit()

    if issue_new and new_number:
        notify(
            "ZSAD_DETACHED",
            f"Z-SAD {old_zsad} retired for BL {reviewed['bl_number']}. "
            f"New Z-SAD {new_number} issued. {len(cancelled_numbers)} invoice(s) cancelled.",
            reviewed_id,
        )
        notify("ZSAD_GENERATED", f"Replacement Z-SAD {new_number} generated for BL {reviewed['bl_number']}.", new_zsad_id)
    else:
        notify(
            "ZSAD_DETACHED",
            f"Z-SAD {old_zsad} detached from BL {reviewed['bl_number']}. {len(cancelled_numbers)} invoice(s) cancelled.",
            reviewed_id,
        )
    audit("DETACH_ZSAD", "reviewed_bl", reviewed_id)
    updated = get_reviewed_bl(reviewed_id)
    updated["detach_summary"] = {
        "old_zsad": old_zsad,
        "new_zsad": new_number,
        "cancelled_invoices": cancelled_numbers,
        "cancelled_count": len(cancelled_numbers),
    }
    return updated


def detach_zsad_for_reupload(reviewed_id: str) -> dict:
    """Cancel the BL/Z-SAD journey so the BL number can be uploaded again."""
    reviewed = get_reviewed_bl(reviewed_id)
    if not reviewed:
        raise ValueError(f"Unknown reviewed BL id: {reviewed_id}")
    status = reviewed.get("status") or ""
    if status not in {"REVIEWED_ZSAD_ISSUED", "AWAITING_PAYMENT"}:
        if status == "CARGO_RELEASED":
            raise ValueError("Cannot detach Z-SAD after cargo release has been issued.")
        if status == "SETTLED_RELEASE_PENDING":
            raise ValueError("Cannot detach Z-SAD after settlement while cargo release is pending.")
        if status == "SETTLED":
            raise ValueError("Cannot detach Z-SAD after payment settlement.")
        raise ValueError("Z-SAD detachment is only available before settlement.")
    old_zsad = reviewed.get("z_sad_number")
    open_invoices = rows(
        "SELECT invoice_number FROM invoices WHERE reviewed_bl_id = ? AND status != 'CANCELLED'",
        (reviewed_id,),
    )
    cancelled_numbers = [inv["invoice_number"] for inv in open_invoices]
    cancelled = cancel_bl_for_reupload(
        reviewed["bl_id"],
        "BL has an Issue",
        reason_detail="Z-SAD replacement requested; cancel old BL so it can be uploaded again.",
        company_id=reviewed.get("company_id") or DEMO_COMPANY_ID,
    )
    cancelled["detach_summary"] = {
        "old_zsad": old_zsad,
        "new_zsad": None,
        "cancelled_invoices": cancelled_numbers,
        "cancelled_count": len(cancelled_numbers),
    }
    notify(
        "ZSAD_DETACHED",
        f"Z-SAD {old_zsad} detached and BL {display_bl_number(cancelled)} cancelled for re-upload.",
        reviewed_id,
        company_id=reviewed.get("company_id") or DEMO_COMPANY_ID,
    )
    audit("DETACH_ZSAD_FOR_REUPLOAD", "reviewed_bl", reviewed_id, company_id=reviewed.get("company_id") or DEMO_COMPANY_ID)
    return cancelled


def invoice_download_url(invoice_id: str) -> str:
    path = f"/download/invoice/{invoice_id}.pdf"
    base = (os.getenv("PUBLIC_APP_URL") or "").strip().rstrip("/")
    if not base or "127.0.0.1" in base or "localhost" in base:
        return path
    return f"{base}{path}"


def invoice_gn83_total(invoice: dict) -> float:
    """GN 83 invoice total (admin + VAT, ceiled)."""
    return float(invoice.get("total") or 0)


def invoice_capitalpay_number(invoice: dict) -> str:
    """Human-readable CapitalPay invoice reference for display and sharing."""
    return (
        invoice.get("capitalpay_ref")
        or invoice.get("capitalpay_urn")
        or "-"
    )


_CHECKOUT_HTML_CACHE: dict[str, str] = {}
_CHECKOUT_CACHE_DIR = DATA_DIR / "capitalpay-checkouts"


def _checkout_cache_path(invoice_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(invoice_id or "invoice"))
    return _CHECKOUT_CACHE_DIR / f"{safe_id}.html"


def _read_checkout_cache(invoice_id: str) -> str | None:
    if invoice_id in _CHECKOUT_HTML_CACHE:
        return _CHECKOUT_HTML_CACHE[invoice_id]
    path = _checkout_cache_path(invoice_id)
    if path.is_file():
        html = path.read_text(encoding="utf-8", errors="replace")
        _CHECKOUT_HTML_CACHE[invoice_id] = html
        return html
    return None


def _write_checkout_cache(invoice_id: str, html: str) -> None:
    _CHECKOUT_HTML_CACHE[invoice_id] = html
    _CHECKOUT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _checkout_cache_path(invoice_id).write_text(html, encoding="utf-8")


def invoice_pay_url(invoice: dict) -> str | None:
    """Importer-facing payment link through the ZCAMS checkout route."""
    invoice_id = (invoice or {}).get("id")
    if not invoice_id:
        return None
    base = (os.getenv("PUBLIC_APP_URL") or "http://127.0.0.1:8050").strip().rstrip("/")
    return f"{base}/capitalpay/checkout/{invoice_id}"


def _capitalpay_checkout_params(invoice: dict) -> dict[str, str]:
    bill_ref = invoice_capitalpay_number(invoice) or invoice.get("invoice_number")
    amount = float(invoice.get("payable_amount") or invoice.get("total") or 0)
    client_name = invoice.get("beneficiary_name") or invoice.get("consignee_name") or "ZCAMS Importer"
    return capitalpay.build_checkout_params(
        client_name=client_name,
        client_msisdn=invoice.get("contact_phone"),
        client_email=invoice.get("contact_email") or invoice.get("consignee_email"),
        client_id_number=invoice.get("consignee_tin") or invoice.get("z_sad_number") or bill_ref,
        amount=amount,
        currency="USD",
        bill_ref_number=bill_ref,
        bill_desc=f"ZCAMS payment for {invoice.get('invoice_number')} | BL {invoice.get('bl_number')}",
    )


def set_invoice_capitalpay_ref(invoice_id: str, capitalpay_ref: str) -> dict:
    """Persist the checkout reference displayed by CapitalPay and refresh the PDF."""
    capitalpay_ref = str(capitalpay_ref or "").strip().upper()
    if not capitalpay_ref:
        return get_invoice(invoice_id)
    with connect() as conn:
        conn.execute("UPDATE invoices SET capitalpay_urn = ? WHERE id = ?", (capitalpay_ref, invoice_id))
        conn.execute("UPDATE payments SET capitalpay_ref = ? WHERE invoice_id = ?", (capitalpay_ref, invoice_id))
        conn.commit()
    try:
        ensure_invoice_pdf(invoice_id)
    except Exception:
        pass
    return get_invoice(invoice_id)


def prepare_capitalpay_checkout(invoice_id: str) -> dict:
    """Prepare checkout once and align ZCAMS/PDF refs with CapitalPay's displayed payment ref."""
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise ValueError(f"Unknown invoice id: {invoice_id}")
    cached_html = _read_checkout_cache(invoice_id)
    if cached_html:
        cached_ref = capitalpay.extract_checkout_payment_ref(cached_html)
        if cached_ref and cached_ref != invoice_capitalpay_number(invoice):
            invoice = set_invoice_capitalpay_ref(invoice_id, cached_ref)
        return {"html": cached_html, "invoice": invoice, "payment_ref": invoice_capitalpay_number(invoice)}

    html = capitalpay.fetch_checkout_page(_capitalpay_checkout_params(invoice))
    checkout_ref = capitalpay.extract_checkout_payment_ref(html) or invoice_capitalpay_number(invoice)
    if checkout_ref and checkout_ref != invoice_capitalpay_number(invoice):
        invoice = set_invoice_capitalpay_ref(invoice_id, checkout_ref)
    _write_checkout_cache(invoice_id, html)
    return {"html": html, "invoice": invoice, "payment_ref": checkout_ref}


def list_invoices_for_user(user: dict | None = None) -> list[dict]:
    """Company-scoped invoice list; super admins see every company."""
    user = user or {}
    if user.get("role") == "SUPER_ADMIN":
        return list_invoices(company_id=None)
    company_id = user.get("company_id") or DEMO_COMPANY_ID
    return list_invoices(company_id=company_id)


def invoice_capitalpay_checkout(invoice: dict) -> float | None:
    """Amount charged at CapitalPay checkout when higher than the GN 83 total."""
    gn83 = invoice_gn83_total(invoice)
    payable = float(invoice.get("payable_amount") or invoice.get("payment_amount") or gn83)
    if payable > gn83 + 0.001:
        return payable
    return None


def invoice_share_message(invoice: dict) -> str:
    invoice_type = (invoice.get("invoice_type") or "").replace("_", " ").title()
    capitalpay_no = invoice_capitalpay_number(invoice)
    gn83_total = invoice_gn83_total(invoice)
    checkout = invoice_capitalpay_checkout(invoice)
    lines = [
        f"ZCAMS {invoice_type} Invoice {invoice.get('invoice_number')}",
        f"BL: {invoice.get('bl_number')} | Z-SAD: {invoice.get('z_sad_number')}",
        f"Amount due: USD {gn83_total:,.2f}",
        f"CapitalPay Invoice No: {capitalpay_no}",
        f"Download PDF: {invoice_download_url(invoice['id'])}",
    ]
    if checkout is not None:
        lines.append(f"CapitalPay checkout: USD {checkout:,.2f} (includes payment processing)")
    if invoice.get("beneficiary_name"):
        lines.append(
            f"Beneficiary: {invoice['beneficiary_name']} | {invoice.get('beneficiary_bank_name')} "
            f"| {invoice.get('beneficiary_account_number')}"
        )
    pay_url = invoice_pay_url(invoice)
    if pay_url:
        lines.append(f"Pay here: {pay_url}")
    return "\n".join(lines)


def invoice_whatsapp_link(invoice_id: str, phone: str | None = None) -> str:
    invoice = get_invoice(invoice_id)
    target = phone or invoice.get("contact_phone") or get_company().get("whatsapp") or get_company().get("phone")
    return whatsapp_url(target, invoice_share_message(invoice))


def invoice_sms_link(invoice_id: str, phone: str | None = None) -> str:
    invoice = get_invoice(invoice_id)
    target = phone or invoice.get("contact_phone") or get_company().get("phone")
    return sms_url(target, invoice_share_message(invoice))


def invoice_email_link(invoice_id: str, email: str | None = None) -> str:
    invoice = get_invoice(invoice_id)
    target = email or invoice.get("contact_email") or invoice.get("consignee_email")
    subject = f"ZCAMS Invoice {invoice.get('invoice_number')} - {invoice.get('z_sad_number')}"
    return mailto_url(target, subject, invoice_share_message(invoice))


def share_invoice_with_importer(
    invoice_id: str,
    channels: list[str] | None = None,
    contact_email: str | None = None,
) -> dict:
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise ValueError(f"Unknown invoice id: {invoice_id}")
    selected = {str(channel).upper() for channel in (channels or [])}
    results: dict[str, dict] = {}
    phone = invoice.get("contact_phone")
    message = invoice_share_message(invoice)

    if "WHATSAPP" in selected:
        link = invoice_whatsapp_link(invoice_id, phone)
        results["whatsapp"] = {"mode": "link", "url": link, "sent": True}
        notify("INVOICE_SHARED", f"Invoice {invoice['invoice_number']} shared via WhatsApp.", invoice_id)

    if "SMS" in selected or "TXT" in selected:
        sms_result = send_sms(phone or "", message)
        results["sms"] = {**sms_result, "url": sms_result.get("link") or invoice_sms_link(invoice_id, phone)}
        notify("INVOICE_SHARED", f"Invoice {invoice['invoice_number']} prepared for SMS.", invoice_id)

    if "EMAIL" in selected or "MAIL" in selected:
        email = (contact_email or invoice.get("contact_email") or "").strip()
        if email:
            recipient_name = invoice.get("consignee_name") or invoice.get("bl_number") or "Importer"
            subject, text, html = invoice_share_email(
                recipient_name=recipient_name,
                message=message,
                invoice_number=invoice["invoice_number"],
            )
            pdf_path = None
            try:
                pdf_path = ensure_invoice_pdf(invoice_id)
            except (ValueError, OSError):
                pdf_path = None
            attachments = [pdf_path] if pdf_path and pdf_path.is_file() else None
            mail_result = send_email(
                email,
                subject,
                text,
                html=html,
                recipient_name=recipient_name,
                attachments=attachments,
                attachment_names=[f"{invoice['invoice_number']}.pdf"] if attachments else None,
                description=f"ZCAMS invoice {invoice['invoice_number']}",
            )
            results["email"] = {
                **mail_result,
                "url": invoice_email_link(invoice_id, email) if not mail_result.get("sent") else "",
            }
        else:
            results["email"] = {
                "sent": False,
                "mode": "mailto",
                "url": invoice_email_link(invoice_id, None),
                "reason": "No importer email supplied; enter client email on the invoice form.",
            }
        if results.get("email", {}).get("sent"):
            notify("INVOICE_SHARED", f"Invoice {invoice['invoice_number']} emailed to {email}.", invoice_id)
        else:
            notify("INVOICE_SHARED", f"Invoice {invoice['invoice_number']} share via email attempted.", invoice_id)

    return results


def generate_invoice(
    reviewed_id: str,
    invoice_type: str,
    std_min_fee_override: float | None = None,
    contact_phone: str | None = None,
    contact_email: str | None = None,
    beneficiary_name: str | None = None,
    beneficiary_bank_name: str | None = None,
    beneficiary_account_number: str | None = None,
) -> dict:
    invoice_type = (invoice_type or "FULL_SETTLEMENT").strip().upper()
    if invoice_type != "FULL_SETTLEMENT":
        raise ValueError("Only Full Settlement invoices are supported.")
    reviewed = get_reviewed_bl(reviewed_id)
    if not reviewed:
        raise ValueError(f"Unknown reviewed BL id: {reviewed_id}")
    quote = gn83_quote_for_reviewed(reviewed)
    if quote.get("exempt"):
        raise ValueError(
            "GN 83 exempt cargo (fertiliser, petroleum, sugar, or in-house clearance). "
            "Z-SAD remains active; settlement invoice is not required."
        )
    minimum_std = round(float(quote["std_min_fee"]), 2)
    std = round(float(std_min_fee_override if std_min_fee_override is not None else minimum_std), 2)
    if std < minimum_std:
        raise ValueError(f"Full Settlement amount cannot be below USD {minimum_std:,.2f}.")
    calc = calculate_invoice(std, invoice_type)
    invoice_id = new_id("inv")
    invoice_number = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    customer_name = beneficiary_name or reviewed.get("consignee_name") or "ZCAMS Importer"
    id_number = reviewed.get("consignee_tin") or reviewed.get("z_sad_number") or invoice_number
    try:
        signed = capitalpay.create_signed_invoice(
            client_invoice_ref=invoice_number,
            amount=calc["total"],
            invoice_type=invoice_type,
            calc=calc,
            customer_name=customer_name,
            email=contact_email,
            msisdn=contact_phone,
            id_number=id_number,
            bl_number=reviewed.get("bl_number") or "",
            z_sad_number=reviewed.get("z_sad_number") or "",
            settlement_account=beneficiary_account_number if invoice_type == "FULL_SETTLEMENT" else None,
        )
    except capitalpay.CapitalPayError as exc:
        raise ValueError(f"CapitalPay signing failed: {exc}") from exc

    # Production safety: refuse to persist mock invoices unless CAPITALPAY_MODE
    # is explicitly 'mock'. This stops dummy CPAYMOCK… invoices from ever
    # being emailed to real importers if the runtime is misconfigured.
    capitalpay_number = signed.get("invoice_number") or ""
    if os.getenv("CAPITALPAY_MODE", "real").strip().lower() != "mock" and (
        signed.get("mode") == "mock" or capitalpay_number.startswith("CPAYMOCK")
    ):
        raise ValueError(
            "Refusing to issue a dummy CapitalPay invoice in production "
            "(CAPITALPAY_MODE is not 'mock'). Check CapitalPay credentials."
        )
    checkout = capitalpay.create_checkout_link(
        invoice_id,
        reviewed["z_sad_number"],
        calc["total"],
        capitalpay_invoice_number=signed["invoice_number"],
    )
    checkout_url = signed.get("checkout_url") or checkout["checkout_url"]
    capitalpay_ref = signed.get("invoice_number") or checkout["reference"]
    payable_total = float(signed.get("amount_expected") or calc["total"])
    pdf_path = ""
    try:
        draft = {
            "id": invoice_id,
            "company_id": reviewed.get("company_id") or DEMO_COMPANY_ID,
            "invoice_number": invoice_number,
            "invoice_type": invoice_type,
            "capitalpay_urn": signed["urn"],
            "status": "AWAITING_PAYMENT",
            "bl_number": reviewed.get("bl_number"),
            "z_sad_number": reviewed.get("z_sad_number"),
            "consignee_name": reviewed.get("consignee_name"),
            "consignee_tin": reviewed.get("consignee_tin"),
            "contact_phone": contact_phone,
            "contact_email": contact_email,
            "beneficiary_name": beneficiary_name,
            "beneficiary_bank_name": beneficiary_bank_name,
            "beneficiary_account_number": beneficiary_account_number,
            "std_min_fee": calc["std_min_fee"],
            "admin_fee": calc["admin_fee"],
            "vat": calc["vat"],
            "total": calc["total"],
            "payable_amount": payable_total,
            "checkout_url": checkout_url,
            "signed_at": signed["signed_at"],
            "due_date": (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat(),
        }
        pdf_path = str(generate_invoice_pdf(draft, get_company(draft["company_id"])))
    except Exception:
        pdf_path = ""

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO invoices (
              id, reviewed_bl_id, z_sad_id, invoice_number, invoice_type,
              std_min_fee, admin_fee, vat, total, payable_amount, contact_phone, contact_email,
              beneficiary_name, beneficiary_bank_name, beneficiary_account_number,
              status, capitalpay_urn, checkout_url, pdf_path, due_date, signed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                reviewed_id,
                reviewed["z_sad_id"],
                invoice_number,
                invoice_type,
                calc["std_min_fee"],
                calc["admin_fee"],
                calc["vat"],
                calc["total"],
                payable_total,
                contact_phone,
                contact_email,
                beneficiary_name,
                beneficiary_bank_name,
                beneficiary_account_number,
                "AWAITING_PAYMENT",
                signed["urn"],
                checkout_url,
                pdf_path,
                (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat(),
                signed["signed_at"],
            ),
        )
        conn.execute(
            """
            INSERT INTO payments (id, invoice_id, payment_type, amount, status, capitalpay_ref, secure_link)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (new_id("pay"), invoice_id, "LINK", payable_total, "PENDING", capitalpay_ref, checkout_url),
        )
        conn.execute("UPDATE reviewed_bls SET status = 'AWAITING_PAYMENT' WHERE id = ?", (reviewed_id,))
        conn.commit()
    notify("INVOICE_GENERATED", f"Invoice {invoice_number} issued for Z-SAD {reviewed['z_sad_number']}. Amount: USD {calc['total']:,.2f}.", invoice_id)
    audit("GENERATE_INVOICE", "invoice", invoice_id)
    return get_invoice(invoice_id)


def list_invoices(company_id: str | None = DEMO_COMPANY_ID) -> list[dict]:
    """List invoices; pass company_id=None for all companies (super admin)."""
    query = """
        SELECT inv.*, rb.bl_id, bl.bl_number, bl.consignee_name, bl.company_id,
               zs.z_sad_number, pay.secure_link, pay.capitalpay_ref,
               c.name AS company_name
        FROM invoices inv
        JOIN reviewed_bls rb ON rb.id = inv.reviewed_bl_id
        JOIN bills_of_lading bl ON bl.id = rb.bl_id
        JOIN z_sads zs ON zs.id = inv.z_sad_id
        LEFT JOIN payments pay ON pay.invoice_id = inv.id
        LEFT JOIN companies c ON c.id = bl.company_id
    """
    params: tuple[Any, ...] = ()
    if company_id is not None:
        query += " WHERE bl.company_id = ?"
        params = (company_id,)
    query += " ORDER BY inv.created_at DESC"
    return rows(query, params)


def get_invoice(invoice_id: str) -> dict:
    invoice = row(
        """
        SELECT inv.*, rb.bl_id, bl.bl_number, bl.consignee_name, bl.consignee_tin, bl.company_id,
               ci.gn83_category, ci.description AS cargo_description,
               zs.z_sad_number, pay.secure_link, pay.status AS payment_status,
               pay.amount AS payment_amount, pay.capitalpay_ref
        FROM invoices inv
        JOIN reviewed_bls rb ON rb.id = inv.reviewed_bl_id
        JOIN bills_of_lading bl ON bl.id = rb.bl_id
        JOIN z_sads zs ON zs.id = inv.z_sad_id
        LEFT JOIN cargo_items ci ON ci.bl_id = bl.id
        LEFT JOIN payments pay ON pay.invoice_id = inv.id
        WHERE inv.id = ?
        """,
        (invoice_id,),
    ) or {}
    if invoice and not invoice.get("payable_amount"):
        invoice["payable_amount"] = invoice.get("payment_amount") or invoice.get("total")
    return invoice


def ensure_invoice_pdf(invoice_id: str) -> Path:
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise ValueError(f"Unknown invoice id: {invoice_id}")
    # Always rebuild from DB so PDF reflects current totals (avoids stale $0 PDFs).
    path = generate_invoice_pdf(invoice, get_company(invoice.get("company_id") or DEMO_COMPANY_ID))
    execute("UPDATE invoices SET pdf_path = ? WHERE id = ?", (str(path), invoice_id))
    return path


def settle_invoice(invoice_id: str) -> dict:
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise ValueError(f"Unknown invoice id: {invoice_id}")
    release_status = "CARGO_RELEASED" if invoice["invoice_type"] == "FULL_SETTLEMENT" else "SETTLED_RELEASE_PENDING"
    with connect() as conn:
        conn.execute("UPDATE invoices SET status = 'SETTLED' WHERE id = ?", (invoice_id,))
        conn.execute(
            "UPDATE payments SET status = 'SETTLED', settled_at = ? WHERE invoice_id = ?",
            (now_iso(), invoice_id),
        )
        conn.execute("UPDATE reviewed_bls SET status = ? WHERE id = ?", (release_status, invoice["reviewed_bl_id"]))
        conn.commit()
    notify("PAYMENT_SETTLED", f"Invoice {invoice['invoice_number']} SETTLED. Amount: USD {invoice['total']:,.2f}.", invoice_id)
    if invoice["invoice_type"] == "FULL_SETTLEMENT":
        notify("CARGO_RELEASED", f"Cargo Release issued for BL {invoice['bl_number']} automatically after full settlement.", invoice["reviewed_bl_id"])
    return get_invoice(invoice_id)


def issue_cargo_release(reviewed_id: str) -> None:
    from services.gn83 import is_gn83_exempt

    reviewed = get_reviewed_bl(reviewed_id)
    if not reviewed:
        raise ValueError(f"Unknown reviewed BL id: {reviewed_id}")
    status = reviewed.get("status") or ""
    cargo = (reviewed.get("cargo_items") or [{}])[0]
    exempt = is_gn83_exempt(cargo.get("gn83_category"))
    if status not in {"SETTLED_RELEASE_PENDING", "REVIEWED_ZSAD_ISSUED"}:
        raise ValueError("Cargo release is not available for the current BL status.")
    if status == "REVIEWED_ZSAD_ISSUED" and not exempt:
        raise ValueError("Settlement invoice must be completed before cargo release.")
    execute("UPDATE reviewed_bls SET status = 'CARGO_RELEASED' WHERE id = ?", (reviewed_id,))
    notify("CARGO_RELEASED", f"Cargo Release issued for BL {reviewed.get('bl_number')} by Admin ZCAMS.", reviewed_id)


def payment_whatsapp_link(invoice_id: str, phone: str | None = None) -> str:
    return invoice_whatsapp_link(invoice_id, phone)


def list_notifications(limit: int | None = None, company_id: str | None = DEMO_COMPANY_ID) -> list[dict]:
    query = """
        SELECT n.*, c.name AS company_name
        FROM notifications n
        LEFT JOIN companies c ON c.id = n.company_id
    """
    params: tuple[Any, ...] = ()
    if company_id is not None:
        query += " WHERE n.company_id = ?"
        params = (company_id,)
    query += " ORDER BY n.created_at DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    return rows(query, params)


def add_certificate(
    name: str,
    file_name: str = "",
    company_id: str = DEMO_COMPANY_ID,
    contents: str | None = None,
) -> dict:
    cert_id = new_id("cert")
    file_url = store_uploaded_document(company_id, file_name or f"{name}.txt", contents)
    execute(
        "INSERT INTO certificates (id, company_id, name, file_name, file_url, uploaded_by) VALUES (?, ?, ?, ?, ?, ?)",
        (cert_id, company_id, name, file_name, file_url, DEMO_USER_ID),
    )
    notify("CERTIFICATE_UPLOADED", f"Certificate '{name}' uploaded.", cert_id, company_id)
    return row("SELECT * FROM certificates WHERE id = ?", (cert_id,)) or {}


def list_certificates(company_id: str = DEMO_COMPANY_ID) -> list[dict]:
    return rows("SELECT * FROM certificates WHERE company_id = ? ORDER BY uploaded_at DESC", (company_id,))


def get_certificate(cert_id: str, company_id: str | None = None) -> dict:
    query = "SELECT * FROM certificates WHERE id = ?"
    params: tuple[Any, ...] = (cert_id,)
    if company_id is not None:
        query += " AND company_id = ?"
        params = (cert_id, company_id)
    return row(query, params) or {}


def rename_certificate(cert_id: str, name: str, company_id: str = DEMO_COMPANY_ID) -> dict:
    if not str(name or "").strip():
        raise ValueError("Document name is required.")
    cert = get_certificate(cert_id, company_id)
    if not cert:
        raise ValueError("Document not found.")
    execute("UPDATE certificates SET name = ? WHERE id = ? AND company_id = ?", (name.strip(), cert_id, company_id))
    notify("CERTIFICATE_RENAMED", f"Document renamed to '{name.strip()}'.", cert_id, company_id)
    return get_certificate(cert_id, company_id)


def delete_certificate(cert_id: str, company_id: str = DEMO_COMPANY_ID) -> None:
    cert = get_certificate(cert_id, company_id)
    if not cert:
        raise ValueError("Document not found.")
    execute("DELETE FROM certificates WHERE id = ? AND company_id = ?", (cert_id, company_id))
    notify("CERTIFICATE_DELETED", f"Document '{cert.get('name')}' deleted.", cert_id, company_id)


def certificate_preview_url(cert_id: str) -> str:
    base = os.getenv("PUBLIC_APP_URL", "http://127.0.0.1:8050").rstrip("/")
    return f"{base}/download/document/{cert_id}"


def update_company_logo(company_id: str, filename: str, contents: str | None) -> dict:
    if not filename:
        raise ValueError("Select a logo file before uploading.")
    logo_path = _store_invoice_ready_logo(company_id, filename, contents)
    execute("UPDATE companies SET logo_path = ? WHERE id = ?", (logo_path, company_id))
    notify("COMPANY_LOGO_UPDATED", "Company logo updated.", company_id, company_id)
    audit("UPDATE_COMPANY_LOGO", "company", company_id, company_id=company_id)
    return get_company(company_id)


def company_logo_url(company_id: str = DEMO_COMPANY_ID) -> str | None:
    company = get_company(company_id)
    if not company.get("logo_path"):
        return None
    base = os.getenv("PUBLIC_APP_URL", "http://127.0.0.1:8050").rstrip("/")
    return f"{base}/download/company-logo/{company_id}"


def compliance_score(company_id: str = DEMO_COMPANY_ID) -> int:
    company = get_company(company_id)
    fields = [
        "name", "pacra_number", "tpin", "zra_licence", "company_email", "phone",
        "address_line1", "city", "province", "bank_name", "account_number", "account_holder",
    ]
    filled = sum(1 for field in fields if company.get(field))
    doc_bonus = min(len(list_certificates(company_id)), 6)
    return round(((filled + doc_bonus) / (len(fields) + 6)) * 100)


def create_contract(
    importer_name: str,
    importer_phone: str = "",
    importer_email: str = "",
    terms: str = "",
    shipment_details: str = "",
    services: str = "",
    fees: str = "",
    company_id: str = DEMO_COMPANY_ID,
) -> dict:
    contract_id = new_id("contract")
    contract_no = _new_contract_no()
    otp = _new_contract_otp()
    otp_hash, otp_salt = hash_password(otp)
    qr_url = contract_sign_url(contract_id, importer_email)
    execute(
        """
        INSERT INTO contracts (
          id, company_id, contract_no, importer_name, importer_phone,
          importer_email, terms, shipment_details, services, fees, qr_url,
          otp_hash, otp_salt
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            contract_id,
            company_id,
            contract_no,
            importer_name,
            importer_phone,
            importer_email,
            terms,
            shipment_details,
            services,
            fees,
            qr_url,
            otp_hash,
            otp_salt,
        ),
    )
    notify("CONTRACT_CREATED", f"Contract {contract_no} created for {importer_name}.", contract_id, company_id)
    contract = row("SELECT * FROM contracts WHERE id = ?", (contract_id,)) or {}
    contract["otp"] = otp
    return contract


def sign_contract(contract_id: str, signed_by: str = "Importer") -> None:
    contract = row("SELECT * FROM contracts WHERE id = ?", (contract_id,))
    if not contract:
        raise ValueError("Contract not found.")
    contract_hash = contract_fingerprint(
        contract,
        signed_email=contract.get("importer_email") or "",
        signature_name=signed_by,
        signature_text=signed_by,
        signature_file_path=contract.get("signature_file_path") or "",
    )
    execute(
        """
        UPDATE contracts
        SET status = 'SIGNED',
            signed_by = ?,
            signature_name = ?,
            signature_text = COALESCE(signature_text, ?),
            contract_hash = ?,
            signed_at = ?
        WHERE id = ?
        """,
        (signed_by, signed_by, signed_by, contract_hash, now_iso(), contract_id),
    )
    notify("CONTRACT_SIGNED", f"Contract {contract.get('contract_no')} signed by {signed_by}.", contract_id, contract.get("company_id") or DEMO_COMPANY_ID)


def list_contracts(company_id: str | None = DEMO_COMPANY_ID) -> list[dict]:
    query = "SELECT * FROM contracts"
    params: tuple[Any, ...] = ()
    if company_id is not None:
        query += " WHERE company_id = ?"
        params = (company_id,)
    query += " ORDER BY created_at DESC"
    return rows(query, params)


def count_unedited_contracts(company_id: str | None = DEMO_COMPANY_ID) -> int:
    query = "SELECT COUNT(*) AS count FROM contracts WHERE status = 'DRAFT'"
    params: tuple[Any, ...] = ()
    if company_id is not None:
        query += " AND company_id = ?"
        params = (company_id,)
    result = row(query, params)
    return int((result or {}).get("count") or 0)


def bulk_registration_visibility(limit: int = 100) -> dict:
    """Engagement analytics for CFA admins created through registration flows."""
    user_rows = rows(
        """
        WITH click_stats AS (
          SELECT user_id, COUNT(*) AS link_clicks, MAX(created_at) AS last_clicked_at
          FROM registration_link_events
          WHERE user_id IS NOT NULL
          GROUP BY user_id
        ),
        login_stats AS (
          SELECT user_id,
                 COUNT(*) AS login_attempts,
                 SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successful_logins,
                 SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failed_logins,
                 MAX(created_at) AS last_login_attempt_at
          FROM login_events
          WHERE user_id IS NOT NULL
          GROUP BY user_id
        )
        SELECT u.id, u.company_id, c.name AS company_name, u.first_name, u.last_name,
               u.email, u.username, u.status, u.created_at,
               COALESCE(cs.link_clicks, 0) AS link_clicks,
               cs.last_clicked_at,
               COALESCE(ls.login_attempts, 0) AS login_attempts,
               COALESCE(ls.successful_logins, 0) AS successful_logins,
               COALESCE(ls.failed_logins, 0) AS failed_logins,
               ls.last_login_attempt_at
        FROM users u
        LEFT JOIN companies c ON c.id = u.company_id
        LEFT JOIN click_stats cs ON cs.user_id = u.id
        LEFT JOIN login_stats ls ON ls.user_id = u.id
        WHERE u.role = 'COMPANY_ADMIN'
        ORDER BY COALESCE(ls.last_login_attempt_at, cs.last_clicked_at, u.created_at) DESC
        LIMIT ?
        """,
        (limit,),
    )
    click_rows = rows(
        """
        SELECT rle.created_at, rle.source, rle.email, rle.ip_address,
               u.email AS user_email, u.first_name, u.last_name, c.name AS company_name
        FROM registration_link_events rle
        LEFT JOIN users u ON u.id = rle.user_id
        LEFT JOIN companies c ON c.id = u.company_id
        ORDER BY rle.created_at DESC
        LIMIT 20
        """
    )
    login_rows = rows(
        """
        SELECT le.created_at, le.email, le.success, le.failure_reason, le.ip_address,
               u.email AS user_email, u.first_name, u.last_name, u.role, c.name AS company_name
        FROM login_events le
        LEFT JOIN users u ON u.id = le.user_id
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE u.role = 'COMPANY_ADMIN' OR le.user_id IS NULL
        ORDER BY le.created_at DESC
        LIMIT 20
        """
    )
    total_admins = len(user_rows)
    clicked_users = sum(1 for item in user_rows if int(item.get("link_clicks") or 0) > 0)
    attempted_users = sum(1 for item in user_rows if int(item.get("login_attempts") or 0) > 0)
    successful_users = sum(1 for item in user_rows if int(item.get("successful_logins") or 0) > 0)
    return {
        "summary": {
            "company_admins": total_admins,
            "link_clicks": sum(int(item.get("link_clicks") or 0) for item in user_rows),
            "clicked_users": clicked_users,
            "not_clicked": max(total_admins - clicked_users, 0),
            "login_attempts": sum(int(item.get("login_attempts") or 0) for item in user_rows),
            "attempted_users": attempted_users,
            "successful_users": successful_users,
            "failed_logins": sum(int(item.get("failed_logins") or 0) for item in user_rows),
        },
        "users": user_rows,
        "clicks": click_rows,
        "logins": login_rows,
    }


def default_contract_terms() -> str:
    if DEFAULT_CONTRACT_TERMS_PATH.is_file():
        return DEFAULT_CONTRACT_TERMS_PATH.read_text(encoding="utf-8").strip()
    return "Standard customs clearance services terms and conditions."


def shipment_payload(
    *,
    shipment_route: str = "",
    bl_reference: str = "",
    cargo: str = "",
    origin: str = "",
    destination: str = "",
    expected_clearance_scope: str = "",
) -> str:
    payload = {
        "shipment_route": shipment_route.strip(),
        "bl_reference": bl_reference.strip(),
        "cargo": cargo.strip(),
        "origin": origin.strip(),
        "destination": destination.strip(),
        "expected_clearance_scope": expected_clearance_scope.strip(),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def parse_shipment_details(value: str | None) -> dict[str, str]:
    defaults = {
        "shipment_route": "",
        "bl_reference": "",
        "cargo": "",
        "origin": "",
        "destination": "",
        "expected_clearance_scope": "",
    }
    if not value:
        return defaults
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        defaults["expected_clearance_scope"] = value or ""
        return defaults
    if not isinstance(parsed, dict):
        return defaults
    return {key: str(parsed.get(key) or "") for key in defaults}


def contract_whatsapp_link(contract_id: str) -> str:
    contract = row("SELECT * FROM contracts WHERE id = ?", (contract_id,)) or {}
    return contract_whatsapp_url(contract)


def contract_whatsapp_url(contract: dict) -> str:
    return whatsapp_url(contract.get("importer_phone"), contract_share_message(contract))


def _new_contract_no() -> str:
    for _ in range(20):
        contract_no = f"CTR-{datetime.now().year}-{random.randint(10000, 99999)}"
        if not row("SELECT id FROM contracts WHERE contract_no = ?", (contract_no,)):
            return contract_no
    return f"CTR-{datetime.now().year}-{uuid.uuid4().hex[:8].upper()}"


def _new_contract_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _public_app_base_url() -> str:
    """Public site URL for emails and signing links (same as invoice PDF/share URLs)."""
    return (
        os.getenv("PUBLIC_APP_URL")
        or os.getenv("ZCAMS_PUBLIC_URL")
        or os.getenv("APP_BASE_URL")
        or os.getenv("DASH_BASE_URL")
        or "http://127.0.0.1:8050"
    ).strip().rstrip("/")


def contract_sign_url(contract_id: str, importer_email: str | None = None) -> str:
    params = {"contract": contract_id}
    if importer_email:
        params["email"] = importer_email
    return f"{_public_app_base_url()}/contract-sign?{urlencode(params)}"


def contract_preview_url(contract_id: str) -> str:
    return f"{_public_app_base_url()}/preview/contract/{contract_id}"


def contract_download_url(contract_id: str) -> str:
    return f"{_public_app_base_url()}/download/contract/{contract_id}.html"


def get_contract(contract_id: str) -> dict | None:
    return row("SELECT * FROM contracts WHERE id = ?", (contract_id,))


def get_contract_by_no(contract_no: str) -> dict | None:
    return row("SELECT * FROM contracts WHERE contract_no = ?", ((contract_no or "").strip(),))


def contract_share_message(contract: dict) -> str:
    return (
        "ZCAMS contract signature request\n\n"
        f"Importer: {contract.get('importer_name')}\n"
        f"Contract ID: {contract.get('contract_no')}\n"
        f"Registered email: {contract.get('importer_email') or '-'}\n"
        f"OTP: {contract.get('otp') or 'Use the OTP sent to your registered contact.'}\n\n"
        "Open the secure signing link, confirm your email, Contract ID, and OTP, then sign:\n"
        f"{contract.get('qr_url') or contract_sign_url(contract.get('id'), contract.get('importer_email'))}"
    )


def contract_email(contract: dict) -> tuple[str, str, str]:
    subject = f"ZCAMS Contract {contract.get('contract_no')} signature request"
    text = contract_share_message(contract)
    html = (
        f"<p>Dear <strong>{contract.get('importer_name')}</strong>,</p>"
        f"<p>Your clearing and forwarding agent has prepared a ZCAMS contract for review and signature.</p>"
        f"<table style='border-collapse:collapse;margin:16px 0'>"
        f"<tr><td style='padding:6px 12px;font-weight:600'>Contract ID</td><td style='padding:6px 12px'>{contract.get('contract_no')}</td></tr>"
        f"<tr><td style='padding:6px 12px;font-weight:600'>Registered email</td><td style='padding:6px 12px'>{contract.get('importer_email') or '-'}</td></tr>"
        f"<tr><td style='padding:6px 12px;font-weight:600'>OTP</td><td style='padding:6px 12px'><code>{contract.get('otp') or 'Sent separately'}</code></td></tr>"
        f"</table>"
        f"<p><a href='{contract.get('qr_url')}' style='display:inline-block;padding:10px 16px;background:#0c270c;color:#fff;border-radius:8px;text-decoration:none'>Review and sign contract</a></p>"
        f"<p>Regards,<br/><strong>ZCAMS</strong></p>"
    )
    return subject, text, html


def render_contract_html(contract_id: str) -> str:
    contract = get_contract(contract_id)
    if not contract:
        raise ValueError("Contract not found.")
    company = get_company(contract.get("company_id") or DEMO_COMPANY_ID)
    shipment = parse_shipment_details(contract.get("shipment_details"))
    logo_url = company_logo_url(contract.get("company_id") or DEMO_COMPANY_ID) or ""
    zcams_logo = "/assets/zcams-logo.png"

    def esc(value: Any) -> str:
        return html_tools.escape(str(value or "-"))

    def block(title: str, value: str) -> str:
        return f"<section><h3>{esc(title)}</h3><p>{esc(value)}</p></section>"

    terms = html_tools.escape(contract.get("terms") or default_contract_terms()).replace("\n", "<br>")
    status = esc(contract.get("status"))
    fingerprint = esc(contract.get("contract_hash") or "Generated after signature")
    signature = esc(contract.get("signature_text") or contract.get("signed_by") or "Pending")

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>ZCAMS Contract {esc(contract.get('contract_no'))}</title>
  <style>
    body {{ margin: 0; background: #f5fbf3; color: #0d190b; font-family: Inter, Segoe UI, Arial, sans-serif; }}
    .page {{ max-width: 980px; margin: 32px auto; padding: 0 18px; }}
    .contract {{ background: #fff; border: 1px solid #cfe5c7; border-radius: 22px; padding: 28px; box-shadow: 0 24px 60px rgba(13,25,11,.12); }}
    .header {{ display: grid; grid-template-columns: 96px 1fr 96px; gap: 18px; align-items: center; border-bottom: 1px solid #cfe5c7; padding-bottom: 18px; }}
    .logo {{ max-width: 92px; max-height: 74px; object-fit: contain; }}
    .eyebrow {{ text-transform: uppercase; letter-spacing: .14em; font-size: 11px; font-weight: 800; color: #ef7d00; margin: 0 0 6px; }}
    h1 {{ margin: 0; font-size: 28px; }}
    h2 {{ margin: 22px 0 12px; font-size: 18px; }}
    h3 {{ margin: 0 0 8px; color: #263522; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 18px 0; }}
    .item, section {{ border: 1px solid #eaf6e5; border-radius: 14px; padding: 12px; background: #fbfef9; }}
    .label {{ color: #53624f; font-size: 11px; text-transform: uppercase; letter-spacing: .08em; font-weight: 800; }}
    .value {{ margin-top: 5px; font-weight: 650; white-space: pre-wrap; }}
    .terms {{ max-height: 520px; overflow: auto; border: 1px solid #cfe5c7; border-radius: 16px; padding: 16px; line-height: 1.55; }}
    .signature {{ font-family: "Brush Script MT", "Segoe Script", cursive; font-size: 42px; color: #0c270c; }}
    .hash {{ word-break: break-all; font-family: Consolas, monospace; font-size: 12px; }}
    @media print {{ body {{ background: #fff; }} .page {{ margin: 0; max-width: none; }} .contract {{ box-shadow: none; border: none; }} .terms {{ max-height: none; }} }}
  </style>
</head>
<body>
  <main class="page">
    <article class="contract">
      <header class="header">
        <img src="{zcams_logo}" class="logo" alt="ZCAMS">
        <div>
          <p class="eyebrow">ZCAMS Signed Contract</p>
          <h1>{esc(contract.get('contract_no'))}</h1>
          <p>{esc(company.get('name') or 'Clearing & Forwarding Agent')}</p>
        </div>
        {f'<img src="{html_tools.escape(logo_url)}" class="logo" alt="Company logo">' if logo_url else '<div></div>'}
      </header>

      <div class="grid">
        <div class="item"><div class="label">Importer</div><div class="value">{esc(contract.get('importer_name'))}</div></div>
        <div class="item"><div class="label">Email</div><div class="value">{esc(contract.get('importer_email'))}</div></div>
        <div class="item"><div class="label">WhatsApp</div><div class="value">{esc(contract.get('importer_phone'))}</div></div>
        <div class="item"><div class="label">Status</div><div class="value">{status}</div></div>
      </div>

      <h2>Shipment Details</h2>
      <div class="grid">
        <div class="item"><div class="label">Shipment Route</div><div class="value">{esc(shipment.get('shipment_route'))}</div></div>
        <div class="item"><div class="label">BL Reference</div><div class="value">{esc(shipment.get('bl_reference'))}</div></div>
        <div class="item"><div class="label">Cargo</div><div class="value">{esc(shipment.get('cargo'))}</div></div>
        <div class="item"><div class="label">Origin</div><div class="value">{esc(shipment.get('origin'))}</div></div>
        <div class="item"><div class="label">Destination</div><div class="value">{esc(shipment.get('destination'))}</div></div>
        <div class="item"><div class="label">Clearance Scope</div><div class="value">{esc(shipment.get('expected_clearance_scope'))}</div></div>
      </div>

      <h2>Services & Fees</h2>
      {block('Services', contract.get('services') or 'No service details supplied.')}
      {block('Fees', contract.get('fees') or 'No fee details supplied.')}

      <h2>Attached Terms of Contract</h2>
      <div class="terms">{terms}</div>

      <h2>Signature</h2>
      <div class="grid">
        <div class="item"><div class="label">Signed By</div><div class="value">{esc(contract.get('signed_by'))}</div></div>
        <div class="item"><div class="label">Signed Email</div><div class="value">{esc(contract.get('signed_email'))}</div></div>
        <div class="item"><div class="label">Signed At</div><div class="value">{esc(contract.get('signed_at'))}</div></div>
      </div>
      <div class="item"><div class="label">Written Signature</div><div class="signature">{signature}</div></div>

      <h2>Cryptographic Fingerprint</h2>
      <div class="item"><div class="hash">{fingerprint}</div></div>
    </article>
  </main>
</body>
</html>"""


def contract_pdf_path(contract: dict) -> Path:
    target_dir = DATA_DIR / "contracts"
    target_dir.mkdir(parents=True, exist_ok=True)
    contract_no = safe_filename(contract.get("contract_no") or contract.get("id") or "contract")
    return target_dir / f"{contract.get('id')}_{contract_no}.pdf"


def ensure_contract_pdf(contract_id: str) -> Path:
    contract = get_contract(contract_id)
    if not contract:
        raise ValueError("Contract not found.")
    target = contract_pdf_path(contract)
    if target.is_file():
        return target

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    title = ParagraphStyle("ContractTitle", parent=styles["Heading1"], fontSize=18, textColor=colors.HexColor("#0c270c"))
    heading = ParagraphStyle("ContractHeading", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#263522"))
    body = ParagraphStyle("ContractBody", parent=styles["BodyText"], fontSize=8.5, leading=11)
    small = ParagraphStyle("ContractSmall", parent=styles["BodyText"], fontSize=7.5, leading=10, textColor=colors.HexColor("#53624f"))

    shipment = parse_shipment_details(contract.get("shipment_details"))
    company = get_company(contract.get("company_id") or DEMO_COMPANY_ID)

    def esc(value: Any) -> str:
        return html_tools.escape(str(value or "-")).replace("\n", "<br/>")

    story = [
        Paragraph("ZCAMS Contract", title),
        Paragraph(f"{esc(contract.get('contract_no'))} | {esc(company.get('name') or 'Clearing & Forwarding Agent')}", small),
        Spacer(1, 8 * mm),
        Paragraph("Client Details", heading),
        Table(
            [
                ["Importer", esc(contract.get("importer_name")), "Email", esc(contract.get("importer_email"))],
                ["WhatsApp", esc(contract.get("importer_phone")), "Status", esc(contract.get("status"))],
            ],
            colWidths=[28 * mm, 62 * mm, 28 * mm, 62 * mm],
        ),
        Spacer(1, 6 * mm),
        Paragraph("Shipment Details", heading),
        Table(
            [
                ["Shipment Route", esc(shipment.get("shipment_route"))],
                ["BL Reference", esc(shipment.get("bl_reference"))],
                ["Cargo", esc(shipment.get("cargo"))],
                ["Origin", esc(shipment.get("origin"))],
                ["Destination", esc(shipment.get("destination"))],
                ["Clearance Scope", esc(shipment.get("expected_clearance_scope"))],
            ],
            colWidths=[42 * mm, 138 * mm],
        ),
        Spacer(1, 6 * mm),
        Paragraph("Services", heading),
        Paragraph(esc(contract.get("services") or "No service details supplied."), body),
        Spacer(1, 4 * mm),
        Paragraph("Fees & Payment Terms", heading),
        Paragraph(esc(contract.get("fees") or "No fee details supplied."), body),
        Spacer(1, 4 * mm),
        Paragraph("Attached Terms of Contract", heading),
        Paragraph(esc(contract.get("terms") or default_contract_terms()), body),
    ]

    if contract.get("status") == "SIGNED":
        story.extend(
            [
                Spacer(1, 6 * mm),
                Paragraph("Signature", heading),
                Paragraph(f"Signed by {esc(contract.get('signed_by'))} at {esc(contract.get('signed_at'))}", body),
                Paragraph(f"SHA-256 fingerprint: {esc(contract.get('contract_hash'))}", small),
            ]
        )

    for item in story:
        if isinstance(item, Table):
            item.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cfe5c7")),
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfef9")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )

    doc = SimpleDocTemplate(str(target), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    doc.build(story)
    return target


def send_contract_to_importer(contract_id: str, *, attach_pdf: bool = False) -> dict:
    contract = get_contract(contract_id)
    if not contract:
        raise ValueError("Contract not found.")
    if contract.get("sent_at"):
        try:
            last_sent = datetime.fromisoformat(contract["sent_at"])
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - last_sent < timedelta(seconds=8):
                contract_copy = dict(contract)
                return {
                    "contract": contract_copy,
                    "email": {
                        "sent": False,
                        "mode": "dedupe",
                        "reason": "Contract was just sent. Duplicate send blocked.",
                    },
                    "whatsapp": contract_whatsapp_url(contract_copy),
                }
        except ValueError:
            pass
    return _send_contract_email(contract_id, attach_pdf=attach_pdf)


def send_contract_review_email(contract_id: str, *, attach_pdf: bool = True) -> dict:
    return _send_contract_email(contract_id, attach_pdf=attach_pdf)


def _send_contract_email(contract_id: str, *, attach_pdf: bool) -> dict:
    contract = get_contract(contract_id)
    if not contract:
        raise ValueError("Contract not found.")
    otp = _new_contract_otp()
    otp_hash, otp_salt = hash_password(otp)
    qr_url = contract_sign_url(contract_id, contract.get("importer_email"))
    execute(
        """
        UPDATE contracts
        SET otp_hash = ?, otp_salt = ?, otp_sent_at = ?, qr_url = ?
        WHERE id = ?
        """,
        (otp_hash, otp_salt, now_iso(), qr_url, contract_id),
    )
    contract = get_contract(contract_id) or {}
    contract["otp"] = otp
    subject, text, html = contract_email(contract)
    attachments = None
    attachment_names = None
    attached_pdf = False
    if attach_pdf:
        pdf_path = ensure_contract_pdf(contract_id)
        attachments = [pdf_path]
        attachment_names = [f"ZCAMS-Contract-{safe_filename(contract.get('contract_no') or contract_id)}.pdf"]
        attached_pdf = True

    email_result = send_email(
        contract.get("importer_email") or "",
        subject,
        text,
        html=html,
        recipient_name=contract.get("importer_name"),
        attachments=attachments,
        attachment_names=attachment_names,
        description="ZCAMS contract signature request",
    )
    if email_result.get("sent"):
        execute(
            "UPDATE contracts SET sent_at = ?, status = 'SENT' WHERE id = ?",
            (now_iso(), contract_id),
        )
    notify(
        "CONTRACT_SENT",
        f"Contract {contract.get('contract_no')} sent to {contract.get('importer_name')}.",
        contract_id,
        contract.get("company_id") or DEMO_COMPANY_ID,
    )
    return {
        "contract": contract,
        "email": email_result,
        "whatsapp": contract_whatsapp_url(contract),
        "attached_pdf": attached_pdf,
    }


def _verify_contract_otp(contract: dict, otp: str) -> bool:
    if not contract.get("otp_hash") or not contract.get("otp_salt"):
        return False
    candidate, _salt = hash_password((otp or "").strip(), contract.get("otp_salt"))
    return secrets.compare_digest(candidate, contract.get("otp_hash") or "")


def contract_fingerprint(
    contract: dict,
    *,
    signed_email: str,
    signature_name: str,
    signature_text: str,
    signature_file_path: str = "",
) -> str:
    payload = {
        "contract_no": contract.get("contract_no"),
        "company_id": contract.get("company_id"),
        "importer_name": contract.get("importer_name"),
        "importer_email": contract.get("importer_email"),
        "importer_phone": contract.get("importer_phone"),
        "shipment_details": contract.get("shipment_details") or "",
        "services": contract.get("services") or "",
        "fees": contract.get("fees") or "",
        "terms": contract.get("terms") or "",
        "signed_email": signed_email.strip().lower(),
        "signature_name": signature_name.strip(),
        "signature_text": signature_text.strip(),
        "signature_file_path": signature_file_path,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sign_contract_with_otp(
    *,
    contract_no: str,
    email: str,
    otp: str,
    signature_name: str,
    signature_text: str,
    signature_file_contents: str | None = None,
    signature_file_name: str | None = None,
    contract_id: str | None = None,
) -> dict:
    contract = get_contract_by_no(contract_no)
    if not contract and contract_id:
        contract = get_contract(contract_id)
    if not contract and (contract_no or "").startswith("contract-"):
        contract = get_contract(contract_no)
    if not contract:
        raise ValueError("Contract ID was not found.")
    if contract.get("status") == "SIGNED":
        raise ValueError("This contract has already been signed.")
    if (email or "").strip().lower() != (contract.get("importer_email") or "").strip().lower():
        raise ValueError("Email does not match the contract recipient.")
    if not _verify_contract_otp(contract, otp):
        raise ValueError("The OTP is invalid. Use the 6-digit code sent to the registered contact.")
    if not signature_name or not signature_name.strip():
        raise ValueError("Typed name is required to confirm signature.")
    if not signature_text or not signature_text.strip():
        raise ValueError("Written signature is required.")

    signature_file_path = ""
    if signature_file_contents and signature_file_name:
        signature_file_path = store_uploaded_document(
            contract.get("company_id") or DEMO_COMPANY_ID,
            f"signature-{contract.get('contract_no')}-{signature_file_name}",
            signature_file_contents,
        )
    contract_hash = contract_fingerprint(
        contract,
        signed_email=email,
        signature_name=signature_name,
        signature_text=signature_text,
        signature_file_path=signature_file_path,
    )
    execute(
        """
        UPDATE contracts
        SET status = 'SIGNED',
            signed_email = ?,
            signed_by = ?,
            signature_name = ?,
            signature_text = ?,
            signature_file_path = ?,
            contract_hash = ?,
            signed_at = ?
        WHERE id = ?
        """,
        (
            email.strip().lower(),
            signature_name.strip(),
            signature_name.strip(),
            signature_text.strip(),
            signature_file_path,
            contract_hash,
            now_iso(),
            contract["id"],
        ),
    )
    notify(
        "CONTRACT_SIGNED",
        f"Contract {contract.get('contract_no')} signed by {signature_name.strip()}.",
        contract["id"],
        contract.get("company_id") or DEMO_COMPANY_ID,
    )
    return get_contract(contract["id"]) or {}


def create_support_ticket(
    subject: str,
    description: str,
    linked_module: str,
    priority: str,
    *,
    company_id: str = DEMO_COMPANY_ID,
    user_id: str = DEMO_USER_ID,
) -> dict:
    ticket_id = new_id("ticket")
    execute(
        """
        INSERT INTO support_tickets (id, company_id, subject, description, linked_module, priority, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ticket_id, company_id, subject, description, linked_module, priority, user_id),
    )
    notify("SUPPORT_TICKET_CREATED", f"Support ticket '{subject}' created.", ticket_id, company_id)
    return row("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,)) or {}


def update_ticket_status(ticket_id: str, status: str) -> None:
    existing = row("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,))
    if not existing:
        raise ValueError("Support ticket not found.")
    resolved_at = now_iso() if status == "Resolved" else None
    execute("UPDATE support_tickets SET status = ?, resolved_at = ? WHERE id = ?", (status, resolved_at, ticket_id))
    notify("SUPPORT_TICKET_UPDATED", f"Support ticket '{existing.get('subject')}' is now {status}.", ticket_id, existing["company_id"])
    audit("UPDATE_SUPPORT_TICKET", "support_ticket", ticket_id, status, company_id=existing["company_id"])


def list_support_tickets(company_id: str | None = None, search: str | None = None) -> list[dict]:
    query = """
        SELECT st.*, c.name AS company_name, u.email AS created_by_email
        FROM support_tickets st
        LEFT JOIN companies c ON c.id = st.company_id
        LEFT JOIN users u ON u.id = st.created_by
    """
    filters: list[str] = []
    params: list[Any] = []
    if company_id is not None:
        filters.append("st.company_id = ?")
        params.append(company_id)
    if search:
        q = f"%{search.strip()}%"
        filters.append(
            "(st.subject LIKE ? OR st.description LIKE ? OR st.linked_module LIKE ? OR st.priority LIKE ? OR st.status LIKE ? OR c.name LIKE ?)"
        )
        params.extend([q, q, q, q, q, q])
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY st.created_at DESC"
    return rows(query, tuple(params))


def classify_chat_response(question: str, answer: str, mode: str | None = None) -> str:
    text = (answer or "").lower()
    if "zcams will not answer" in text or "i do not know and i do not have any idea" in text:
        return "Bad Response"
    if mode in {"faq", "tutorial", "retrieval", "local-model"} and len((answer or "").strip()) >= 24:
        return "Good Response"
    if "please use the relevant zcams module" in text or "raise a support ticket" in text:
        return "Neutral Response"
    if mode in {"fallback", "governed"}:
        return "Neutral Response"
    return "Neutral Response"


def record_chat_event(question: str, answer: str, mode: str, quality: str, user: dict | None = None) -> dict:
    event_id = new_id("chat")
    user = user or {}
    execute(
        """
        INSERT INTO chat_events (id, company_id, user_id, question, answer, mode, quality)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            user.get("company_id") or DEMO_COMPANY_ID,
            user.get("id") or DEMO_USER_ID,
            question,
            answer,
            mode,
            quality,
        ),
    )
    return row("SELECT * FROM chat_events WHERE id = ?", (event_id,)) or {}


def list_chat_events(search: str | None = None, limit: int = 250) -> list[dict]:
    query = """
        SELECT ce.*, c.name AS company_name, u.email AS user_email, u.role AS user_role
        FROM chat_events ce
        LEFT JOIN companies c ON c.id = ce.company_id
        LEFT JOIN users u ON u.id = ce.user_id
    """
    params: list[Any] = []
    if search:
        q = f"%{search.strip()}%"
        query += " WHERE ce.question LIKE ? OR ce.answer LIKE ? OR ce.mode LIKE ? OR ce.quality LIKE ? OR c.name LIKE ? OR u.email LIKE ?"
        params.extend([q, q, q, q, q, q])
    query += " ORDER BY ce.created_at DESC LIMIT ?"
    params.append(int(limit))
    return rows(query, tuple(params))


def save_chat_context_upload(filename: str, contents: str, user: dict | None = None) -> dict:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "zcams-chat-context.txt").strip("._") or "zcams-chat-context.txt"
    suffix = Path(safe_name).suffix.lower()
    if suffix not in {".txt", ".md", ".docx"}:
        raise ValueError("Upload TXT, MD, or DOCX context files only.")
    try:
        _prefix, encoded = (contents or "").split(",", 1)
        data = base64.b64decode(encoded)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Could not read the uploaded context file.") from exc
    if not data:
        raise ValueError("Uploaded context file is empty.")
    if len(data) > 2_000_000:
        raise ValueError("Context upload is too large. Use a file below 2 MB.")
    context_dir = UPLOAD_DIR / "chat-context"
    context_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}_{safe_name}"
    output_path = context_dir / output_name
    output_path.write_bytes(data)
    clear_document_cache()
    audit("UPLOAD_CHAT_CONTEXT", "chat_context", output_name, company_id=(user or {}).get("company_id") or DEMO_COMPANY_ID)
    return {"file_name": safe_name, "stored_as": output_name, "size": len(data), "path": str(output_path)}


def chat_answer(question: str, history: list[dict] | None = None, user: dict | None = None) -> str:
    result = answer_question(question, history=history)
    answer = result["answer"]
    mode = result.get("mode") or "unknown"
    quality = classify_chat_response(question, answer, mode)
    record_chat_event(question, answer, mode, quality, user=user)
    return answer
