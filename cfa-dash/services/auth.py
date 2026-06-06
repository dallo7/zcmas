"""Server-side sessions, login audit, and role-based access control for ZCAMS."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import has_request_context, request, session

from services.db import connect
from services.repository import DEMO_USER_ID, normalize_role, row, rows, new_id, now_iso


ROLE_SUPER_ADMIN = "SUPER_ADMIN"
ROLE_ADMIN = "ADMIN"
ROLE_OPERATIONS = "OPERATIONS"
ROLE_COMPANY_ADMIN = "COMPANY_ADMIN"
ROLE_DECLARANT = "DECLARANT"

PUBLIC_PATHS = {"/login", "/onboarding", "/contract-sign", "/tutorials"}

OPERATIONAL_PATHS = {
    "/dashboard",
    "/change-password",
    "/bls",
    "/reviewed-bl",
    "/invoices",
    "/checkout",
    "/contracts",
    "/notifications",
    "/support",
    "/chat",
    "/gn83",
    "/tutorials",
}

COMPANY_ADMIN_PATHS = OPERATIONAL_PATHS | {
    "/admin",
    "/company-profile",
    "/change-password",
}

ADMIN_PATHS = {
    "/admin-support",
    "/notifications",
    "/support",
    "/chat",
    "/gn83",
    "/tutorials",
    "/change-password",
}

OPERATIONS_PATHS = {
    "/operations",
    "/tutorials",
    "/change-password",
}

SUPER_ADMIN_PATHS = {
    "/super-admin",
    "/operations",
    "/admin-support",
    *OPERATIONAL_PATHS,
    "/admin",
    "/company-profile",
    "/invoices",
    "/checkout",
    "/contracts",
    "/notifications",
    "/support",
    "/change-password",
}

SESSION_COOKIE = "zcams_sid"
SESSION_HOURS = int(os.getenv("SESSION_LIFETIME_HOURS", "8"))


def configure_server(flask_app) -> None:
    secret = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY")
    if not secret:
        secret = secrets.token_hex(32)
    flask_app.secret_key = secret
    flask_app.config.update(
        SESSION_COOKIE_NAME=SESSION_COOKIE,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=os.getenv("SESSION_COOKIE_SAMESITE", "Lax"),
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=SESSION_HOURS),
    )


def _client_ip() -> str | None:
    if not has_request_context():
        return None
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.remote_addr


def _user_agent() -> str | None:
    if not has_request_context():
        return None
    return (request.headers.get("User-Agent") or "")[:512] or None


def _serialize_user(user: dict) -> dict:
    role = normalize_role(user.get("role"))
    return {
        "id": user["id"],
        "company_id": user.get("company_id"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "username": user.get("username"),
        "email": user.get("email"),
        "phone": user.get("phone"),
        "whatsapp": user.get("whatsapp"),
        "role": role,
        "status": user.get("status"),
        "must_change_password": bool(user.get("must_change_password")),
    }


def get_user_by_id(user_id: str) -> dict | None:
    user = row(
        """
        SELECT id, company_id, first_name, last_name, username, email, phone, whatsapp,
               role, status, must_change_password
        FROM users WHERE id = ? AND status = 'ACTIVE'
        """,
        (user_id,),
    )
    return _serialize_user(user) if user else None


def record_login_event(
    *,
    email: str | None,
    user_id: str | None,
    success: bool,
    failure_reason: str = "",
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO login_events (id, user_id, email, success, ip_address, user_agent, failure_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("login"),
                user_id,
                email,
                1 if success else 0,
                _client_ip(),
                _user_agent(),
                failure_reason or None,
            ),
        )
        conn.commit()


def record_registration_link_click(
    *,
    user_id: str | None,
    email: str | None,
    source: str | None = "registration",
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO registration_link_events (id, user_id, email, source, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("regclick"),
                user_id or None,
                (email or "").strip().lower() or None,
                (source or "registration")[:80],
                _client_ip(),
                _user_agent(),
            ),
        )
        conn.commit()


def create_session(user: dict) -> str:
    token = secrets.token_urlsafe(48)
    expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat()
    session_id = new_id("sess")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO user_sessions (
              id, user_id, session_token, ip_address, user_agent, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, user["id"], token, _client_ip(), _user_agent(), expires),
        )
        conn.commit()
    session.permanent = True
    session["session_token"] = token
    session["user_id"] = user["id"]
    record_login_event(email=user.get("email"), user_id=user["id"], success=True)
    return token


def touch_session(token: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE user_sessions SET last_seen_at = ? WHERE session_token = ? AND revoked_at IS NULL",
            (now_iso(), token),
        )
        conn.commit()


def revoke_session(token: str | None) -> None:
    if not token:
        return
    with connect() as conn:
        conn.execute(
            "UPDATE user_sessions SET revoked_at = ? WHERE session_token = ? AND revoked_at IS NULL",
            (now_iso(), token),
        )
        conn.commit()


def logout_current_session() -> None:
    token = session.pop("session_token", None)
    session.pop("user_id", None)
    revoke_session(token)


def resolve_session_user(token: str | None) -> dict | None:
    if not token:
        return None
    record = row(
        """
        SELECT s.session_token, s.expires_at, s.revoked_at,
               u.id, u.company_id, u.first_name, u.last_name, u.username, u.email,
               u.phone, u.whatsapp, u.role, u.status, u.must_change_password
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.session_token = ? AND u.status = 'ACTIVE'
        """,
        (token,),
    )
    if not record or record.get("revoked_at"):
        return None
    expires = record.get("expires_at")
    if expires:
        try:
            expiry = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= expiry:
                revoke_session(token)
                return None
        except ValueError:
            pass
    touch_session(token)
    return _serialize_user(record)


def current_user() -> dict | None:
    if not has_request_context():
        return None
    token = session.get("session_token")
    user = resolve_session_user(token)
    if user:
        return user
    if token:
        logout_current_session()
    return None


def current_user_id() -> str:
    user = current_user()
    return user["id"] if user else DEMO_USER_ID


def login_user(user: dict) -> dict:
    create_session(user)
    return _serialize_user(user)


def default_home(role: str | None) -> str:
    if normalize_role(role) == ROLE_SUPER_ADMIN:
        return "/super-admin"
    if normalize_role(role) == ROLE_ADMIN:
        return "/admin-support"
    if normalize_role(role) == ROLE_OPERATIONS:
        return "/operations"
    return "/dashboard"


def path_allowed(role: str | None, pathname: str) -> bool:
    path = (pathname or "/").split("#", 1)[0].split("?", 1)[0].rstrip("/") or "/"
    if path in PUBLIC_PATHS:
        return True
    role = normalize_role(role)
    if role == ROLE_SUPER_ADMIN:
        return path in SUPER_ADMIN_PATHS or path.startswith("/super-admin")
    if role == ROLE_ADMIN:
        return path in ADMIN_PATHS
    if role == ROLE_OPERATIONS:
        return path in OPERATIONS_PATHS
    if role == ROLE_COMPANY_ADMIN:
        return path in COMPANY_ADMIN_PATHS
    if role == ROLE_DECLARANT:
        return path in OPERATIONAL_PATHS
    return False


def role_label(role: str | None) -> str:
    role = normalize_role(role)
    if role == ROLE_ADMIN:
        return "Admin Support"
    if role == ROLE_OPERATIONS:
        return "Operations"
    if role == ROLE_DECLARANT:
        return "Declarant / Agent"
    return role.replace("_", " ").title()


def list_login_events(limit: int = 50, *, company_id: str | None = None) -> list[dict]:
    if company_id:
        return rows(
            """
            SELECT le.*, u.first_name, u.last_name, u.email AS user_email, u.role
            FROM login_events le
            LEFT JOIN users u ON u.id = le.user_id
            WHERE u.company_id = ? OR le.user_id IS NULL
            ORDER BY le.created_at DESC
            LIMIT ?
            """,
            (company_id, limit),
        )
    return rows(
        """
        SELECT le.*, u.first_name, u.last_name, u.email AS user_email, u.role, u.company_id
        FROM login_events le
        LEFT JOIN users u ON u.id = le.user_id
        ORDER BY le.created_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def list_active_sessions(limit: int = 50) -> list[dict]:
    return rows(
        """
        SELECT s.*, u.first_name, u.last_name, u.email, u.role, u.company_id
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.revoked_at IS NULL AND datetime(s.expires_at) > datetime('now')
        ORDER BY s.last_seen_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def list_user_sessions(limit: int = 50) -> list[dict]:
    return rows(
        """
        SELECT s.*, u.first_name, u.last_name, u.email, u.role, u.company_id,
               CASE
                 WHEN s.revoked_at IS NOT NULL THEN 'REVOKED'
                 WHEN datetime(s.expires_at) <= datetime('now') THEN 'EXPIRED'
                 ELSE 'ACTIVE'
               END AS session_status
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        ORDER BY s.last_seen_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def list_audit_events(limit: int = 100, *, company_id: str | None = None) -> list[dict]:
    if company_id:
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
    return rows(
        """
        SELECT a.*, u.first_name, u.last_name, u.email AS actor_email, c.name AS company_name
        FROM audit_events a
        LEFT JOIN users u ON u.id = a.user_id
        LEFT JOIN companies c ON c.id = a.company_id
        ORDER BY a.created_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def revoke_user_session(session_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE user_sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (now_iso(), session_id),
        )
        conn.commit()


def restore_user_session(session_id: str) -> None:
    expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat()
    with connect() as conn:
        conn.execute(
            "UPDATE user_sessions SET revoked_at = NULL, expires_at = ?, last_seen_at = ? WHERE id = ?",
            (expires, now_iso(), session_id),
        )
        conn.commit()


def delete_user_session(session_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM user_sessions WHERE id = ?", (session_id,))
        conn.commit()


def install_client_session(client, user: dict) -> None:
    """Bind a server session to a Flask test client (for authenticated download tests)."""
    token = secrets.token_urlsafe(48)
    expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO user_sessions (
              id, user_id, session_token, ip_address, user_agent, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (new_id("sess"), user["id"], token, "127.0.0.1", "pytest", expires),
        )
        conn.commit()
    with client.session_transaction() as flask_sess:
        flask_sess["session_token"] = token
        flask_sess["user_id"] = user["id"]
        flask_sess.permanent = True


def platform_transaction_rows(limit: int = 40) -> list[dict]:
    return rows(
        """
        SELECT
          bl.id AS bl_id,
          bl.bl_number,
          bl.company_id,
          c.name AS company_name,
          bl.status AS bl_status,
          bl.uploaded_at,
          rb.id AS reviewed_id,
          rb.status AS reviewed_status,
          zs.z_sad_number,
          inv.invoice_number,
          inv.status AS invoice_status,
          inv.total AS invoice_total,
          pay.status AS payment_status
        FROM bills_of_lading bl
        LEFT JOIN companies c ON c.id = bl.company_id
        LEFT JOIN reviewed_bls rb ON rb.bl_id = bl.id
        LEFT JOIN z_sads zs ON zs.reviewed_bl_id = rb.id AND zs.is_active = 1
        LEFT JOIN invoices inv ON inv.reviewed_bl_id = rb.id
        LEFT JOIN payments pay ON pay.invoice_id = inv.id
        ORDER BY bl.uploaded_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def cs_lookup_shipment(query: str) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"error": "Enter a BL number, Z-SAD number, or invoice number."}
    bl = row(
        """
        SELECT bl.*, c.name AS company_name, rb.id AS reviewed_id, rb.status AS reviewed_status,
               zs.z_sad_number, inv.invoice_number, inv.status AS invoice_status, inv.total,
               pay.status AS payment_status
        FROM bills_of_lading bl
        LEFT JOIN companies c ON c.id = bl.company_id
        LEFT JOIN reviewed_bls rb ON rb.bl_id = bl.id
        LEFT JOIN z_sads zs ON zs.reviewed_bl_id = rb.id AND zs.is_active = 1
        LEFT JOIN invoices inv ON inv.reviewed_bl_id = rb.id
        LEFT JOIN payments pay ON pay.invoice_id = inv.id
        WHERE bl.bl_number = ? OR zs.z_sad_number = ? OR inv.invoice_number = ?
        ORDER BY bl.uploaded_at DESC
        LIMIT 1
        """,
        (q, q, q),
    )
    if not bl:
        return {"error": f"No shipment found for '{q}'."}
    return {"bl": bl}


def cs_lookup_user(identifier: str) -> dict[str, Any]:
    q = (identifier or "").strip()
    if not q:
        return {"error": "Enter an email or username."}
    user = row(
        """
        SELECT u.*, c.name AS company_name, c.status AS company_status
        FROM users u
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE lower(u.email) = lower(?) OR lower(u.username) = lower(?)
        """,
        (q, q),
    )
    if not user:
        return {"error": f"No user found for '{q}'."}
    logins = rows(
        """
        SELECT success, ip_address, created_at, failure_reason
        FROM login_events
        WHERE lower(email) = lower(?) OR user_id = ?
        ORDER BY created_at DESC
        LIMIT 5
        """,
        (user.get("email") or q, user["id"]),
    )
    user.pop("password_hash", None)
    user.pop("password_salt", None)
    user["role"] = normalize_role(user.get("role"))
    return {"user": user, "recent_logins": logins}
