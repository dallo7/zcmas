from __future__ import annotations

from pathlib import Path

from flask import Response, abort, send_file

from services.db import UPLOAD_DIR
from services.pdf_service import generate_invoice_pdf
from services.repository import ensure_invoice_pdf, get_certificate, get_company, get_contract, get_invoice, render_contract_html


def register_invoice_routes(flask_app) -> None:
    @flask_app.get("/download/invoice/<invoice_id>.pdf")
    def download_invoice_pdf(invoice_id: str):
        invoice = get_invoice(invoice_id)
        if not invoice:
            abort(404)
        try:
            path = ensure_invoice_pdf(invoice_id)
        except Exception as exc:
            abort(500, description=str(exc))
        if not path.is_file():
            abort(404)
        filename = f"ZCAMS-Invoice-{invoice.get('invoice_number', invoice_id)}.pdf"
        return send_file(
            path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    @flask_app.get("/download/document/<cert_id>")
    def preview_company_document(cert_id: str):
        cert = get_certificate(cert_id)
        if not cert or not cert.get("file_url"):
            abort(404)
        path = (UPLOAD_DIR.parent / cert["file_url"]).resolve()
        uploads_root = UPLOAD_DIR.resolve()
        if uploads_root not in path.parents or not path.is_file():
            abort(404)
        return send_file(path, as_attachment=False, download_name=cert.get("file_name") or path.name)

    @flask_app.get("/download/company-logo/<company_id>")
    def preview_company_logo(company_id: str):
        company = get_company(company_id)
        if not company or not company.get("logo_path"):
            abort(404)
        path = (UPLOAD_DIR.parent / company["logo_path"]).resolve()
        uploads_root = UPLOAD_DIR.resolve()
        if uploads_root not in path.parents or not path.is_file():
            abort(404)
        return send_file(path, as_attachment=False, download_name=path.name)

    @flask_app.get("/preview/contract/<contract_id>")
    def preview_signed_contract(contract_id: str):
        contract = get_contract(contract_id)
        if not contract:
            abort(404)
        try:
            html = render_contract_html(contract_id)
        except Exception as exc:
            abort(500, description=str(exc))
        return Response(html, mimetype="text/html")

    @flask_app.get("/download/contract/<contract_id>.html")
    def download_signed_contract(contract_id: str):
        contract = get_contract(contract_id)
        if not contract:
            abort(404)
        try:
            html = render_contract_html(contract_id)
        except Exception as exc:
            abort(500, description=str(exc))
        filename = f"ZCAMS-Contract-{contract.get('contract_no', contract_id)}.html"
        return Response(
            html,
            mimetype="text/html",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
