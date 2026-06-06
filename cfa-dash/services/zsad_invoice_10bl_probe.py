from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "zsad_invoice_10bl_probe_results.json"
PREFIX = "PROBE10BL"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def timed(metrics: dict[str, float], name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        metrics[name] = round((time.perf_counter() - start) * 1000, 2)


def _payloads() -> list[dict[str, Any]]:
    cases = [
        ("001", "20FT_CONTAINER", 1, 27.065, "FULL_SETTLEMENT", "Sea", "Import", "Rice in bags"),
        ("002", "20FT_CONTAINER", 2, 54.13, "FULL_SETTLEMENT", "Sea", "Import", "Two containers of rice"),
        ("003", "LOOSE_LCL", 4, 96.345, "FULL_SETTLEMENT", "Sea", "Import", "Loose/LCL rice cargo"),
        ("004", "40FT_CONTAINER", 3, 81.195, "FULL_SETTLEMENT", "Sea", "Import", "Three forty-foot containers"),
        ("005", "MOTOR_VEHICLE", 1, 2.2, "FULL_SETTLEMENT", "Road", "Import", "Motor vehicle"),
        ("006", "HEAVY_EQUIPMENT", 1, 18.0, "FULL_SETTLEMENT", "Road", "Import", "Heavy equipment"),
        ("007", "DRY_BULK", 0, 42.5, "FULL_SETTLEMENT", "Sea", "Import", "Dry bulk cargo"),
        ("008", "BULK_LIQUID", 0, 65.0, "FULL_SETTLEMENT", "Sea", "Transit", "Bulk liquid"),
        ("009", "LIVE_ANIMAL", 1, 4.0, "FULL_SETTLEMENT", "Road", "Transit", "Live animals"),
        ("010", "GENERAL_CARGO", 0, 1.5, "FULL_SETTLEMENT", "Air", "Export", "General air cargo"),
    ]
    payloads = []
    for suffix, category, containers, weight, invoice_type, transport, route, cargo in cases:
        bl_number = f"{PREFIX}{suffix}"
        payloads.append(
            {
                "bl_number": bl_number,
                "doc_type": "Bill of Lading",
                "route_type": route,
                "transport_mode": transport,
                "zra_regime": "IM4 Home Use" if route == "Import" else "Transit / Export",
                "shipper_name": f"Probe Shipper {suffix}",
                "carrier_name": "Probe Carrier Line",
                "vessel_vehicle_no": f"MV-PROBE-{suffix}",
                "origin": "Dar es Salaam",
                "destination": "Lusaka",
                "consignee_tin": f"1000123{suffix}",
                "consignee_name": f"Probe Importer {suffix}",
                "gross_weight": weight,
                "no_containers": containers,
                "cargo_description": cargo,
                "hs_code": "1006.30",
                "quantity": max(containers, 1),
                "unit": "Shipment",
                "gn83_category": category,
                "file_name": f"{bl_number}.pdf",
                "invoice_type": invoice_type,
            }
        )
    return payloads


def _cleanup(repository, connect, prefix: str = PREFIX) -> None:
    invoices_to_unlink: list[str] = []
    with connect() as conn:
        bl_ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM bills_of_lading WHERE bl_number LIKE ?",
                (f"{prefix}%",),
            ).fetchall()
        ]
        if not bl_ids:
            return
        for bl_id in bl_ids:
            reviewed_ids = [row[0] for row in conn.execute("SELECT id FROM reviewed_bls WHERE bl_id = ?", (bl_id,)).fetchall()]
            for reviewed_id in reviewed_ids:
                invoice_ids = [row[0] for row in conn.execute("SELECT id FROM invoices WHERE reviewed_bl_id = ?", (reviewed_id,)).fetchall()]
                for invoice_id in invoice_ids:
                    pdf = conn.execute("SELECT pdf_path FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
                    if pdf and pdf[0]:
                        invoices_to_unlink.append(pdf[0])
                    conn.execute("DELETE FROM payments WHERE invoice_id = ?", (invoice_id,))
                    conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
                    conn.execute("DELETE FROM notifications WHERE related_entity_id = ?", (invoice_id,))
                conn.execute("DELETE FROM z_sads WHERE reviewed_bl_id = ?", (reviewed_id,))
                conn.execute("DELETE FROM reviewed_bls WHERE id = ?", (reviewed_id,))
                conn.execute("DELETE FROM notifications WHERE related_entity_id = ?", (reviewed_id,))
            conn.execute("DELETE FROM cargo_items WHERE bl_id = ?", (bl_id,))
            conn.execute("DELETE FROM bills_of_lading WHERE id = ?", (bl_id,))
        conn.commit()
    for pdf in invoices_to_unlink:
        try:
            Path(pdf).unlink(missing_ok=True)
        except OSError:
            pass


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def run_probe() -> dict[str, Any]:
    os.environ["CAPITALPAY_MODE"] = "mock"
    os.environ["ZCAMS_ALLOW_MOCK_CAPITALPAY"] = "true"
    os.environ["BIRD_EMAIL_MODE"] = "mock"

    from services import capitalpay, repository
    from services.db import connect

    repository.bootstrap()
    _cleanup(repository, connect)

    results: dict[str, Any] = {
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sample_size": 10,
        "login": {},
        "transactions": [],
        "negative_tests": [],
        "summary": {},
        "cleanup": "probe rows and generated PDFs removed after metrics were collected",
    }

    metrics: dict[str, float] = {}
    with timed(metrics, "valid_login_ms"):
        user = repository.authenticate_user("companyadmin", "demo123")
    with timed(metrics, "invalid_login_ms"):
        invalid_user = repository.authenticate_user("companyadmin", "wrong-password")
    results["login"] = {
        "valid_user": bool(user),
        "role": user.get("role") if user else None,
        "company_id": user.get("company_id") if user else None,
        "invalid_user": bool(invalid_user),
        **metrics,
    }

    created_reviewed: list[dict[str, Any]] = []
    created_invoices: list[dict[str, Any]] = []

    try:
        for index, payload in enumerate(_payloads(), start=1):
            txn_metrics: dict[str, float] = {}
            with timed(txn_metrics, "save_bl_ms"):
                bl = repository.create_bl(payload, auto_review=False, use_ocr_defaults=False)
            with timed(txn_metrics, "issue_zsad_ms"):
                reviewed = repository.review_bl(bl["id"])
            with timed(txn_metrics, "generate_invoice_ms"):
                invoice = repository.generate_invoice(
                    reviewed["id"],
                    payload["invoice_type"],
                    contact_phone="0971234567",
                    contact_email="probe-importer@example.com",
                    beneficiary_name=payload["consignee_name"] if payload["invoice_type"] == "FULL_SETTLEMENT" else None,
                    beneficiary_bank_name="Probe Bank" if payload["invoice_type"] == "FULL_SETTLEMENT" else None,
                    beneficiary_account_number=f"0100{index:06d}" if payload["invoice_type"] == "FULL_SETTLEMENT" else None,
                )
            with timed(txn_metrics, "align_ref_ms"):
                aligned = repository.set_invoice_capitalpay_ref(invoice["id"], f"CPAY10BL{index:03d}")
            with timed(txn_metrics, "pdf_regen_ms"):
                pdf_path = repository.ensure_invoice_pdf(invoice["id"])
            with timed(txn_metrics, "whatsapp_link_ms"):
                whatsapp = repository.invoice_whatsapp_link(invoice["id"], "0971234567")

            created_reviewed.append(reviewed)
            created_invoices.append(aligned)
            results["transactions"].append(
                {
                    "case": index,
                    "bl_number": payload["bl_number"],
                    "route": payload["route_type"],
                    "transport": payload["transport_mode"],
                    "category": payload["gn83_category"],
                    "invoice_type": payload["invoice_type"],
                    "z_sad_number": reviewed.get("z_sad_number"),
                    "invoice_number": aligned.get("invoice_number"),
                    "capitalpay_ref": aligned.get("capitalpay_ref") or aligned.get("capitalpay_urn"),
                    "total_usd": aligned.get("total"),
                    "payable_usd": aligned.get("payable_amount"),
                    "pdf_exists": pdf_path.is_file(),
                    "whatsapp_link": whatsapp.startswith("https://wa.me/"),
                    "status": aligned.get("status"),
                    "metrics_ms": txn_metrics,
                }
            )

        # Negative tests use the created sample where needed, then restore state.
        def record_negative(name: str, error_type: str, meaning: str, fn) -> None:
            start = time.perf_counter()
            try:
                fn()
                outcome = "UNEXPECTED_PASS"
                message = ""
            except Exception as exc:  # noqa: BLE001 - report captures expected operational failures.
                outcome = "EXPECTED_ERROR"
                message = str(exc)
            results["negative_tests"].append(
                {
                    "name": name,
                    "type": error_type,
                    "outcome": outcome,
                    "message": message[:400],
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                    "meaning": meaning,
                }
            )

        first_payload = _payloads()[0]
        first_reviewed = created_reviewed[0]
        first_invoice = created_invoices[0]
        record_negative(
            "Duplicate BL number",
            "VALIDATION / CONFLICT",
            "The platform must prevent a second active journey for a BL that already has a Z-SAD.",
            lambda: repository.create_bl(first_payload, auto_review=False, use_ocr_defaults=False),
        )
        record_negative(
            "Unknown reviewed BL invoice",
            "NOT FOUND",
            "Invoice generation must not proceed for a non-existent reviewed BL.",
            lambda: repository.generate_invoice("reviewed-does-not-exist", "FULL_SETTLEMENT"),
        )
        record_negative(
            "Full settlement below GN 83 minimum",
            "BUSINESS RULE",
            "Operators cannot undercharge the statutory minimum.",
            lambda: repository.generate_invoice(first_reviewed["id"], "FULL_SETTLEMENT", std_min_fee_override=1),
        )

        old_mode = os.environ.get("CAPITALPAY_MODE")
        old_key = os.environ.get("CAPITALPAY_KEY")
        old_secret = os.environ.get("CAPITALPAY_SECRET")
        try:
            os.environ["CAPITALPAY_MODE"] = "real"
            os.environ["CAPITALPAY_KEY"] = ""
            os.environ["CAPITALPAY_SECRET"] = ""
            record_negative(
                "CapitalPay real mode missing credentials",
                "CONFIGURATION",
                "Production must fail closed instead of issuing mock references.",
                lambda: capitalpay.create_signed_invoice(
                    client_invoice_ref="INV-PROBE-FAIL",
                    amount=10,
                    invoice_type="FULL_SETTLEMENT",
                    calc={"std_min_fee": 10, "admin_fee": 2, "vat": 0.32, "total": 3},
                    customer_name="Probe Failure",
                ),
            )
        finally:
            if old_mode is None:
                os.environ.pop("CAPITALPAY_MODE", None)
            else:
                os.environ["CAPITALPAY_MODE"] = old_mode
            if old_key is None:
                os.environ.pop("CAPITALPAY_KEY", None)
            else:
                os.environ["CAPITALPAY_KEY"] = old_key
            if old_secret is None:
                os.environ.pop("CAPITALPAY_SECRET", None)
            else:
                os.environ["CAPITALPAY_SECRET"] = old_secret

        original_fetch = capitalpay.fetch_checkout_page
        try:
            def fail_checkout(_params):
                raise capitalpay.CapitalPayError("Simulated checkout timeout / endpoint not reachable")

            capitalpay.fetch_checkout_page = fail_checkout
            record_negative(
                "CapitalPay checkout endpoint unreachable",
                "NOT REACHABLE / TIMEOUT",
                "Pay Now and PDF download preparation should surface a dependency failure.",
                lambda: repository.prepare_capitalpay_checkout(first_invoice["id"]),
            )
        finally:
            capitalpay.fetch_checkout_page = original_fetch

    finally:
        txns = results["transactions"]
        for stage in ["save_bl_ms", "issue_zsad_ms", "generate_invoice_ms", "align_ref_ms", "pdf_regen_ms", "whatsapp_link_ms"]:
            values = [float(txn["metrics_ms"][stage]) for txn in txns if stage in txn["metrics_ms"]]
            results["summary"][stage] = {
                "min": round(min(values), 2) if values else 0,
                "avg": round(sum(values) / len(values), 2) if values else 0,
                "p95": round(_percentile(values, 95), 2) if values else 0,
                "max": round(max(values), 2) if values else 0,
            }
        results["summary"]["passed_transactions"] = len([txn for txn in txns if txn.get("pdf_exists") and txn.get("whatsapp_link")])
        results["summary"]["failed_transactions"] = len(txns) - results["summary"]["passed_transactions"]
        results["summary"]["negative_expected_errors"] = len(
            [item for item in results["negative_tests"] if item["outcome"] == "EXPECTED_ERROR"]
        )
        _cleanup(repository, connect)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    probe = run_probe()
    print(json.dumps(probe["summary"], indent=2))
    print(OUTPUT)
