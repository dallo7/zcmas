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


def _migrate_users(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    migrations = {
        "username": "ALTER TABLE users ADD COLUMN username TEXT",
        "password_hash": "ALTER TABLE users ADD COLUMN password_hash TEXT",
        "password_salt": "ALTER TABLE users ADD COLUMN password_salt TEXT",
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
