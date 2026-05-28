from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = DATA_DIR / "zcams.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate_users(conn)
        _migrate_invoices(conn)
        _migrate_bl_cancel(conn)
        _migrate_companies(conn)
        _migrate_contracts(conn)
        _migrate_auth(conn)
        _migrate_chat_events(conn)


def _migrate_chat_events(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS chat_events (
          id TEXT PRIMARY KEY,
          company_id TEXT,
          user_id TEXT,
          question TEXT NOT NULL,
          answer TEXT NOT NULL,
          mode TEXT,
          quality TEXT NOT NULL DEFAULT 'Neutral Response',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chat_events_created ON chat_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_chat_events_quality ON chat_events(quality);
        """
    )
    conn.commit()


def _migrate_auth(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          session_token TEXT NOT NULL UNIQUE,
          ip_address TEXT,
          user_agent TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          expires_at TEXT NOT NULL,
          revoked_at TEXT,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token);
        CREATE TABLE IF NOT EXISTS login_events (
          id TEXT PRIMARY KEY,
          user_id TEXT,
          email TEXT,
          success INTEGER NOT NULL DEFAULT 0,
          ip_address TEXT,
          user_agent TEXT,
          failure_reason TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_login_events_created ON login_events(created_at DESC);
        """
    )
    conn.commit()


def _migrate_users(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    migrations = {
        "username": "ALTER TABLE users ADD COLUMN username TEXT",
        "password_hash": "ALTER TABLE users ADD COLUMN password_hash TEXT",
        "password_salt": "ALTER TABLE users ADD COLUMN password_salt TEXT",
        "must_change_password": "ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0",
        "password_changed_at": "ALTER TABLE users ADD COLUMN password_changed_at TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)
    conn.commit()


def _migrate_invoices(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(invoices)").fetchall()}
    migrations = {
        "contact_phone": "ALTER TABLE invoices ADD COLUMN contact_phone TEXT",
        "beneficiary_name": "ALTER TABLE invoices ADD COLUMN beneficiary_name TEXT",
        "beneficiary_bank_name": "ALTER TABLE invoices ADD COLUMN beneficiary_bank_name TEXT",
        "beneficiary_account_number": "ALTER TABLE invoices ADD COLUMN beneficiary_account_number TEXT",
        "contact_email": "ALTER TABLE invoices ADD COLUMN contact_email TEXT",
        "payable_amount": "ALTER TABLE invoices ADD COLUMN payable_amount REAL",
        "pdf_path": "ALTER TABLE invoices ADD COLUMN pdf_path TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)
    conn.commit()


def _migrate_bl_cancel(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(bills_of_lading)").fetchall()}
    migrations = {
        "cancelled_at": "ALTER TABLE bills_of_lading ADD COLUMN cancelled_at TEXT",
        "cancelled_by": "ALTER TABLE bills_of_lading ADD COLUMN cancelled_by TEXT",
        "cancel_reason": "ALTER TABLE bills_of_lading ADD COLUMN cancel_reason TEXT",
        "cancel_reason_detail": "ALTER TABLE bills_of_lading ADD COLUMN cancel_reason_detail TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)
    conn.commit()


def _migrate_companies(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(companies)").fetchall()}
    migrations = {
        "logo_path": "ALTER TABLE companies ADD COLUMN logo_path TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)
    conn.commit()


def _migrate_contracts(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(contracts)").fetchall()}
    migrations = {
        "shipment_details": "ALTER TABLE contracts ADD COLUMN shipment_details TEXT",
        "services": "ALTER TABLE contracts ADD COLUMN services TEXT",
        "fees": "ALTER TABLE contracts ADD COLUMN fees TEXT",
        "otp_hash": "ALTER TABLE contracts ADD COLUMN otp_hash TEXT",
        "otp_salt": "ALTER TABLE contracts ADD COLUMN otp_salt TEXT",
        "otp_sent_at": "ALTER TABLE contracts ADD COLUMN otp_sent_at TEXT",
        "sent_at": "ALTER TABLE contracts ADD COLUMN sent_at TEXT",
        "signed_email": "ALTER TABLE contracts ADD COLUMN signed_email TEXT",
        "signature_name": "ALTER TABLE contracts ADD COLUMN signature_name TEXT",
        "signature_text": "ALTER TABLE contracts ADD COLUMN signature_text TEXT",
        "signature_file_path": "ALTER TABLE contracts ADD COLUMN signature_file_path TEXT",
        "contract_hash": "ALTER TABLE contracts ADD COLUMN contract_hash TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)
    conn.commit()


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]
