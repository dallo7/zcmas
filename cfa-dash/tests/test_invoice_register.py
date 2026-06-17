from unittest.mock import patch

from services import repository
from services.invoice_register import (
    INVOICE_PAGE_SIZE,
    filter_invoice_rows,
    invoice_register_counts,
    paginate_invoice_rows,
)


def _sample_invoices():
    return [
        {
            "id": "inv-1",
            "invoice_number": "INV-001",
            "capitalpay_urn": "CPAY001",
            "bl_number": "BL-001",
            "z_sad_number": "Z-SAD-001",
            "status": "AWAITING_PAYMENT",
            "invoice_type": "FULL_SETTLEMENT",
            "total": 181.0,
            "company_id": repository.DEMO_COMPANY_ID,
        },
        {
            "id": "inv-2",
            "invoice_number": "INV-002",
            "capitalpay_urn": "CPAY002",
            "bl_number": "BL-002",
            "z_sad_number": "Z-SAD-002",
            "status": "SETTLED",
            "invoice_type": "FULL_SETTLEMENT",
            "total": 200.0,
            "company_id": repository.DEMO_COMPANY_ID,
        },
        {
            "id": "inv-3",
            "invoice_number": "INV-003",
            "capitalpay_urn": "CPAY003",
            "bl_number": "BL-003",
            "z_sad_number": "Z-SAD-003",
            "status": "AWAITING_PAYMENT",
            "invoice_type": "FULL_SETTLEMENT",
            "total": 150.0,
            "company_id": repository.DEMO_COMPANY_ID,
        },
    ]


def test_filter_invoice_rows_outstanding():
    invoices = _sample_invoices()
    filtered = filter_invoice_rows(invoices, "outstanding")
    assert len(filtered) == 2
    assert all(inv["status"] != "SETTLED" for inv in filtered)


def test_filter_invoice_rows_search_by_bl():
    invoices = _sample_invoices()
    filtered = filter_invoice_rows(invoices, "all", "BL-002")
    assert len(filtered) == 1
    assert filtered[0]["invoice_number"] == "INV-002"


def test_paginate_invoice_rows():
    invoices = _sample_invoices()
    page_rows, page, total_pages = paginate_invoice_rows(invoices, 1, page_size=2)
    assert len(page_rows) == 2
    assert page == 1
    assert total_pages == 2

    page_rows, page, total_pages = paginate_invoice_rows(invoices, 2, page_size=2)
    assert len(page_rows) == 1
    assert page == 2


def test_invoice_register_counts():
    total, outstanding, settled = invoice_register_counts(_sample_invoices())
    assert total == 3
    assert outstanding == 2
    assert settled == 1


def test_pagination_limits_rows_for_large_register():
    invoices = [
        {
            "id": f"inv-{index}",
            "invoice_number": f"INV-{index:04d}",
            "capitalpay_urn": f"CPAY{index:04d}",
            "bl_number": f"BL-{index:04d}",
            "z_sad_number": f"Z-SAD-{index:04d}",
            "status": "SETTLED" if index % 2 else "AWAITING_PAYMENT",
            "invoice_type": "FULL_SETTLEMENT",
            "total": 100.0,
            "company_id": repository.DEMO_COMPANY_ID,
        }
        for index in range(120)
    ]
    page_rows, page, total_pages = paginate_invoice_rows(invoices, 1)
    assert len(page_rows) == INVOICE_PAGE_SIZE
    assert total_pages == 5
    assert page == 1


def test_invoice_whatsapp_link_from_register_row_avoids_get_invoice():
    invoice = _sample_invoices()[0]
    invoice["contact_phone"] = "0971234567"
    with patch("services.repository.get_invoice") as get_invoice:
        link = repository.invoice_whatsapp_link_from_invoice(invoice)
        get_invoice.assert_not_called()
    assert link.startswith("https://wa.me/")


def test_invoice_page_size_is_reasonable():
    assert INVOICE_PAGE_SIZE >= 10


def test_list_invoices_query_completes_quickly():
    repository.bootstrap()
    import time

    t0 = time.perf_counter()
    rows = repository.list_invoices_for_user({"role": "COMPANY_ADMIN", "company_id": repository.DEMO_COMPANY_ID})
    elapsed = time.perf_counter() - t0
    assert isinstance(rows, list)
    assert elapsed < 2.0, f"list_invoices_for_user took {elapsed:.2f}s"
