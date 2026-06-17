"""Authenticated download routes for ASYCUDA XML CFA clearance exports."""

from __future__ import annotations

from flask import Response, abort

from services.asycuda_xml import (
    WORKFLOW_CLEARANCE,
    WORKFLOW_DECLARATION,
    build_asycuda_xml,
    export_filename,
)
from services.repository import (
    DEMO_COMPANY_ID,
    asycuda_export_context_for_bl,
    asycuda_export_context_for_declaration,
    get_bl,
)


def register_asycuda_routes(flask_app) -> None:
    from services import auth

    @flask_app.get("/download/asycuda/clearance/bl/<bl_id>.xml")
    def download_clearance_xml(bl_id: str):
        return _download_bl_clearance(bl_id, auth)

    @flask_app.get("/download/asycuda/waybill/bl/<bl_id>.xml")
    def download_clearance_xml_legacy(bl_id: str):
        """Legacy path kept for bookmarks; same as clearance export."""
        return _download_bl_clearance(bl_id, auth)

    @flask_app.get("/download/asycuda/declaration/<reviewed_id>.xml")
    def download_declaration_xml(reviewed_id: str):
        user = auth.current_user()
        if not user:
            abort(401)
        try:
            context = asycuda_export_context_for_declaration(reviewed_id)
        except ValueError:
            abort(404)
        bl = context["bl"]
        company_id = bl.get("company_id") or DEMO_COMPANY_ID
        if user.get("role") != "ADMIN" and user.get("company_id") != company_id:
            abort(403)
        status = "DRAFT" if (context.get("reviewed") or {}).get("status") not in {
            "SETTLED",
            "CARGO_RELEASED",
        } else "FINAL"
        xml_body = build_asycuda_xml(
            workflow=WORKFLOW_DECLARATION,
            bl=bl,
            company=context.get("company"),
            cargo_items=context.get("cargo_items") or [],
            containers=context.get("containers") or [],
            reviewed=context.get("reviewed"),
            invoice=context.get("invoice"),
            status=status,
        )
        filename = export_filename(workflow=WORKFLOW_DECLARATION, bl=bl, reviewed=context.get("reviewed"))
        return Response(
            xml_body,
            mimetype="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


def _download_bl_clearance(bl_id: str, auth) -> Response:
    user = auth.current_user()
    if not user:
        abort(401)
    bl = get_bl(bl_id)
    if not bl:
        abort(404)
    company_id = bl.get("company_id") or DEMO_COMPANY_ID
    if user.get("role") != "ADMIN" and user.get("company_id") != company_id:
        abort(403)
    context = asycuda_export_context_for_bl(bl_id)
    status = "DRAFT" if (bl.get("status") or "") == "UPLOADED" else "IN_PROGRESS"
    xml_body = build_asycuda_xml(
        workflow=WORKFLOW_CLEARANCE,
        bl=context["bl"],
        company=context.get("company"),
        cargo_items=context.get("cargo_items") or [],
        status=status,
    )
    filename = export_filename(workflow=WORKFLOW_CLEARANCE, bl=context["bl"])
    return Response(
        xml_body,
        mimetype="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
