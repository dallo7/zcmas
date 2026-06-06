from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from xml.dom import minidom

from services.db import connect, rows_to_dicts
from services.repository import new_id, now_iso


STATUS_ORDER = {"Failed": 0, "Pending": 1, "In-Progress": 2, "Settled": 3}
STATUS_FILTERS = ("All Transactions", "Settled", "Pending", "Failed", "In-Progress")
SETTLEMENT_CURRENCY = "TZS"


def _tzs_rate() -> float:
    try:
        return float(os.getenv("TCAMS_SETTLEMENT_TZS_RATE", "1") or 1)
    except ValueError:
        return 1.0


def _run_window(now: datetime | None = None) -> tuple[str, str]:
    current = now or datetime.now(timezone.utc)
    window_hour = current.hour - (current.hour % 2)
    run_key = current.strftime(f"%Y%m%d{window_hour:02d}")
    run_number = f"Run{(window_hour // 2) + 1:03d}"
    return run_key, run_number


def _status_label(status: str | None) -> str:
    normalized = (status or "Pending").strip().upper().replace("_", "-")
    if normalized in {"SETTLED", "PAID", "SUCCESS"}:
        return "Settled"
    if normalized in {"FAILED", "DECLINED", "CANCELLED"}:
        return "Failed"
    if normalized in {"IN-PROGRESS", "PROCESSING", "RUNNING"}:
        return "In-Progress"
    return "Pending"


def _format_reference(value: str | None) -> str:
    cleaned = "".join(ch for ch in (value or "") if ch.isalnum()).upper()
    return (cleaned or "TCAMS00000")[:10].ljust(10, "0")


def _source_invoice_rows() -> list[dict]:
    with connect() as conn:
        return rows_to_dicts(
            conn.execute(
                """
                SELECT
                  c.id AS company_id,
                  c.name AS company_name,
                  c.zaffa_number,
                  c.zra_licence,
                  c.bank_name,
                  c.branch,
                  c.account_number,
                  inv.id AS invoice_id,
                  inv.invoice_number,
                  inv.std_min_fee,
                  inv.payable_amount,
                  pay.status AS payment_status,
                  pay.amount AS payment_amount,
                  pay.capitalpay_ref,
                  pay.settled_at,
                  bl.bl_number
                FROM invoices inv
                JOIN reviewed_bls rb ON rb.id = inv.reviewed_bl_id
                JOIN bills_of_lading bl ON bl.id = rb.bl_id
                JOIN companies c ON c.id = bl.company_id
                JOIN payments pay ON pay.invoice_id = inv.id
                WHERE inv.status != 'CANCELLED'
                ORDER BY c.name ASC, inv.created_at DESC
                """
            ).fetchall()
        )


def _compile_items(source_rows: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    rate = _tzs_rate()
    for invoice in source_rows:
        company_id = invoice.get("company_id") or "unknown"
        item = grouped.setdefault(
            company_id,
            {
                "company_id": invoice.get("company_id"),
                "cfa_company_name": invoice.get("company_name") or "Unknown CFA",
                "cfa_licence_number": invoice.get("zaffa_number") or invoice.get("zra_licence") or "-",
                "bank_name": invoice.get("bank_name") or "",
                "bank_branch": invoice.get("branch") or "",
                "bank_account_number": invoice.get("account_number") or "",
                "amount_tzs": 0.0,
                "declarations_count": 0,
                "payment_status": "Settled",
                "capitalpay_reference": "",
                "flag_reason": "",
            },
        )
        amount = round(float(invoice.get("std_min_fee") or 0) * rate, 2)
        item["amount_tzs"] = round(float(item["amount_tzs"]) + amount, 2)
        item["declarations_count"] = int(item["declarations_count"]) + 1
        status = _status_label(invoice.get("payment_status"))
        if STATUS_ORDER[status] < STATUS_ORDER[item["payment_status"]]:
            item["payment_status"] = status
        if not item["capitalpay_reference"]:
            item["capitalpay_reference"] = _format_reference(invoice.get("capitalpay_ref") or invoice.get("invoice_number"))

        flags = set(filter(None, str(item.get("flag_reason") or "").split("; ")))
        if not item["bank_name"]:
            flags.add("Missing bank name")
        if not item["bank_account_number"]:
            flags.add("Missing account number")
        if status == "Failed":
            flags.add("Payment failed")
        payable_amount = invoice.get("payable_amount")
        payment_amount = invoice.get("payment_amount")
        if payable_amount is not None and payment_amount is not None:
            if abs(float(payable_amount or 0) - float(payment_amount or 0)) > 0.01:
                flags.add("Amount discrepancy")
        item["flag_reason"] = "; ".join(sorted(flags))
    return list(grouped.values())


def ensure_current_settlement_run() -> dict:
    run_key, run_number = _run_window()
    prepared_at = now_iso()
    source_rows = _source_invoice_rows()
    items = _compile_items(source_rows)
    total_amount = round(sum(float(item["amount_tzs"] or 0) for item in items), 2)

    with connect() as conn:
        existing = conn.execute("SELECT * FROM settlement_runs WHERE run_key = ?", (run_key,)).fetchone()
        if existing:
            run_id = existing["id"]
            conn.execute(
                """
                UPDATE settlement_runs
                SET prepared_at = ?, total_amount_tzs = ?, cfa_count = ?, status = 'PREPARED'
                WHERE id = ?
                """,
                (prepared_at, total_amount, len(items), run_id),
            )
            conn.execute("DELETE FROM settlement_run_items WHERE run_id = ?", (run_id,))
        else:
            run_id = new_id("setrun")
            conn.execute(
                """
                INSERT INTO settlement_runs (id, run_key, run_number, prepared_at, total_amount_tzs, cfa_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, run_key, run_number, prepared_at, total_amount, len(items)),
            )
        for item in items:
            conn.execute(
                """
                INSERT INTO settlement_run_items (
                  id, run_id, company_id, cfa_company_name, cfa_licence_number, bank_name,
                  bank_branch, bank_account_number, amount_tzs, declarations_count,
                  payment_status, capitalpay_reference, flag_reason, last_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("setitem"),
                    run_id,
                    item.get("company_id"),
                    item["cfa_company_name"],
                    item.get("cfa_licence_number"),
                    item.get("bank_name"),
                    item.get("bank_branch"),
                    item.get("bank_account_number"),
                    item["amount_tzs"],
                    item["declarations_count"],
                    item["payment_status"],
                    item.get("capitalpay_reference"),
                    item.get("flag_reason"),
                    prepared_at,
                ),
            )
        conn.commit()
        run = rows_to_dicts(conn.execute("SELECT * FROM settlement_runs WHERE id = ?", (run_id,)).fetchall())[0]
    return run


def settlement_dashboard_data(status_filter: str = "All Transactions", search: str | None = None) -> dict:
    run = ensure_current_settlement_run()
    query = """
        SELECT *
        FROM settlement_run_items
        WHERE run_id = ?
    """
    params: list = [run["id"]]
    if status_filter and status_filter != "All Transactions":
        query += " AND payment_status = ?"
        params.append(status_filter)
    query += " ORDER BY cfa_company_name ASC"
    with connect() as conn:
        items = rows_to_dicts(conn.execute(query, tuple(params)).fetchall())
        logs = rows_to_dicts(
            conn.execute(
                """
                SELECT *
                FROM settlement_download_logs
                WHERE run_id = ?
                ORDER BY downloaded_at DESC
                LIMIT 8
                """,
                (run["id"],),
            ).fetchall()
        )

    needle = (search or "").strip().lower()
    if needle:
        items = [
            item
            for item in items
            if needle in str(item.get("cfa_company_name") or "").lower()
            or needle in str(item.get("cfa_licence_number") or "").lower()
            or needle in str(item.get("bank_name") or "").lower()
            or needle in str(item.get("capitalpay_reference") or "").lower()
        ]

    status_counts = {status: 0 for status in STATUS_FILTERS if status != "All Transactions"}
    for item in items:
        status = item.get("payment_status") or "Pending"
        status_counts[status] = status_counts.get(status, 0) + 1
    flags_count = sum(1 for item in items if item.get("flag_reason"))
    return {
        "run": run,
        "items": items,
        "logs": logs,
        "summary": {
            "total_amount_tzs": round(sum(float(item.get("amount_tzs") or 0) for item in items), 2),
            "cfa_count": len(items),
            "flagged_count": flags_count,
            "status_counts": status_counts,
        },
    }


def settlement_file_name(run: dict) -> str:
    prepared = datetime.fromisoformat(str(run["prepared_at"]).replace("Z", "+00:00"))
    return f"TCAMS_Settlement_{prepared:%Y%m%d}_{run['run_number']}.xml"


def build_settlement_xml(run_id: str) -> tuple[str, str, list[dict], dict]:
    with connect() as conn:
        run_rows = rows_to_dicts(conn.execute("SELECT * FROM settlement_runs WHERE id = ?", (run_id,)).fetchall())
        if not run_rows:
            raise ValueError("Settlement run not found.")
        run = run_rows[0]
        items = rows_to_dicts(
            conn.execute(
                """
                SELECT *
                FROM settlement_run_items
                WHERE run_id = ?
                ORDER BY cfa_company_name ASC
                """,
                (run_id,),
            ).fetchall()
        )
    root = ET.Element(
        "SettlementReport",
        {
            "system": "TCAMS",
            "runNumber": str(run["run_number"]),
            "preparedAt": str(run["prepared_at"]),
            "currency": SETTLEMENT_CURRENCY,
        },
    )
    for item in items:
        beneficiary = ET.SubElement(root, "Beneficiary")
        ET.SubElement(beneficiary, "BeneficiaryName").text = item.get("cfa_company_name") or ""
        ET.SubElement(beneficiary, "BankName").text = item.get("bank_name") or ""
        ET.SubElement(beneficiary, "Branch").text = item.get("bank_branch") or ""
        ET.SubElement(beneficiary, "AccountNumber").text = item.get("bank_account_number") or ""
        ET.SubElement(beneficiary, "Amount").text = f"{float(item.get('amount_tzs') or 0):.2f}"
        ET.SubElement(beneficiary, "Currency").text = SETTLEMENT_CURRENCY
        ET.SubElement(beneficiary, "Reference").text = _format_reference(item.get("capitalpay_reference"))
        ET.SubElement(beneficiary, "Date").text = str(run["prepared_at"])[:10]
    rough_xml = ET.tostring(root, encoding="utf-8")
    pretty_xml = minidom.parseString(rough_xml).toprettyxml(indent="  ")
    return settlement_file_name(run), pretty_xml, items, run


def log_settlement_download(run_id: str, user: dict | None, file_name: str, cfa_count: int, total_amount_tzs: float) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settlement_download_logs (
              id, run_id, user_id, user_email, file_name, cfa_count, total_amount_tzs
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("setdl"),
                run_id,
                (user or {}).get("id"),
                (user or {}).get("email"),
                file_name,
                cfa_count,
                total_amount_tzs,
            ),
        )
        conn.commit()
