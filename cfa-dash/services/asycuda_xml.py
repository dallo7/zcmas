"""Build ASYCUDA-compatible XML exports for ZCAMS CFA clearance workflow backup."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

EXPORT_VERSION = "1.0"
SOURCE_SYSTEM = "ZCAMS"

WORKFLOW_CLEARANCE = "clearance"
WORKFLOW_DECLARATION = "declaration"

SUPPORTED_WORKFLOWS = frozenset({WORKFLOW_CLEARANCE, WORKFLOW_DECLARATION})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _text(parent: ET.Element, tag: str, value: Any) -> ET.Element:
    elem = ET.SubElement(parent, tag)
    if value is not None and str(value).strip():
        elem.text = str(value).strip()
    return elem


def _export_meta(root: ET.Element, *, workflow: str, status: str) -> None:
    meta = ET.SubElement(root, "ExportMeta")
    _text(meta, "Source", SOURCE_SYSTEM)
    _text(meta, "DocumentType", "Clearance" if workflow == WORKFLOW_CLEARANCE else "Declaration")
    _text(meta, "Status", status)
    _text(meta, "ExportedAt", _utc_now())
    _text(meta, "FormatVersion", EXPORT_VERSION)
    _text(
        meta,
        "Note",
        "ZCAMS CFA clearance export for unfinished BL/Z-SAD work. "
        "Save locally as ASYCUDA XML before lodging to prevent data loss.",
    )


def _traders(parent: ET.Element, bl: dict, company: dict | None) -> None:
    traders = ET.SubElement(parent, "Traders")
    consignor = ET.SubElement(traders, "Consignor")
    _text(consignor, "Name", bl.get("shipper_name") or bl.get("company_name"))
    _text(consignor, "TIN", bl.get("consignor_tin"))
    _text(consignor, "Address", bl.get("shipper_address"))
    _text(consignor, "Country", bl.get("shipper_country"))

    consignee = ET.SubElement(traders, "Consignee")
    _text(consignee, "Name", bl.get("consignee_name"))
    _text(consignee, "TIN", bl.get("consignee_tin"))

    declarant = ET.SubElement(traders, "Declarant")
    _text(declarant, "Name", (company or {}).get("name") or bl.get("company_name"))
    _text(declarant, "TPIN", (company or {}).get("tpin"))
    _text(declarant, "ZRAlicence", (company or {}).get("zra_licence") or bl.get("agent_license"))
    _text(declarant, "DeclarantNumber", bl.get("declarant_number"))


def _transport(parent: ET.Element, bl: dict) -> None:
    transport = ET.SubElement(parent, "Transport")
    _text(transport, "Mode", bl.get("transport_mode"))
    _text(transport, "RouteType", bl.get("route_type"))
    _text(transport, "DocumentType", bl.get("doc_type"))
    _text(transport, "ZRARegime", bl.get("zra_regime"))
    _text(transport, "Carrier", bl.get("carrier_name"))
    _text(transport, "VesselOrVehicle", bl.get("vessel_vehicle_no"))
    _text(transport, "Origin", bl.get("origin"))
    _text(transport, "Destination", bl.get("destination"))


def _transport_document(parent: ET.Element, bl: dict) -> None:
    doc = ET.SubElement(parent, "TransportDocument")
    _text(doc, "Reference", bl.get("bl_number"))
    _text(doc, "Type", bl.get("doc_type") or "Bill of Lading")
    _text(doc, "Currency", bl.get("currency"))
    _text(doc, "ConsignmentValue", bl.get("consignment_value"))
    _text(doc, "GrossWeight", bl.get("gross_weight"))
    _text(doc, "ContainerCount", bl.get("no_containers"))


def _goods(parent: ET.Element, bl: dict, cargo_items: list[dict]) -> None:
    goods = ET.SubElement(parent, "Goods")
    if cargo_items:
        for item in cargo_items:
            line = ET.SubElement(goods, "Item")
            _text(line, "Description", item.get("description"))
            _text(line, "HSCode", item.get("hs_code"))
            _text(line, "Quantity", item.get("quantity"))
            _text(line, "Unit", item.get("unit"))
            _text(line, "Weight", item.get("weight"))
            _text(line, "GN83Category", item.get("gn83_category"))
            _text(line, "GN83MinimumUSD", item.get("min_fee_usd"))
    else:
        line = ET.SubElement(goods, "Item")
        _text(line, "Description", bl.get("cargo_description") or "General cargo")
        _text(line, "GN83Category", bl.get("gn83_category"))
        _text(line, "GN83Unit", bl.get("gn83_unit"))
        _text(line, "GN83MinimumUSD", bl.get("gn83_fee_usd"))


def _containers(parent: ET.Element, containers: list[dict], bl: dict) -> None:
    block = ET.SubElement(parent, "Containers")
    count = int(bl.get("no_containers") or 0)
    _text(block, "DeclaredContainerCount", count)
    if containers:
        for container in containers:
            row = ET.SubElement(block, "Container")
            _text(row, "Number", container.get("container_no"))
            _text(row, "Size", container.get("size"))
            _text(row, "Seal", container.get("seal_no"))
    elif count:
        row = ET.SubElement(block, "Container")
        _text(row, "Number", "PENDING")
        _text(row, "Note", "Container numbers not yet captured in ZCAMS")


def _declaration_header(parent: ET.Element, reviewed: dict, invoice: dict | None) -> None:
    ident = ET.SubElement(parent, "Identification")
    _text(ident, "ZSADNumber", reviewed.get("z_sad_number"))
    _text(ident, "ReviewedBLStatus", reviewed.get("status"))
    _text(ident, "ReviewedAt", reviewed.get("reviewed_at"))
    _text(ident, "BLReference", reviewed.get("bl_number"))

    if invoice:
        inv = ET.SubElement(parent, "InvoiceSummary")
        _text(inv, "InvoiceNumber", invoice.get("invoice_number"))
        _text(inv, "InvoiceType", invoice.get("invoice_type"))
        _text(inv, "Status", invoice.get("status"))
        _text(inv, "TotalUSD", invoice.get("total"))
        _text(inv, "CapitalPayURN", invoice.get("capitalpay_urn"))


def build_asycuda_xml(
    *,
    workflow: str,
    bl: dict,
    company: dict | None = None,
    cargo_items: list[dict] | None = None,
    containers: list[dict] | None = None,
    reviewed: dict | None = None,
    invoice: dict | None = None,
    status: str = "DRAFT",
) -> str:
    if workflow not in SUPPORTED_WORKFLOWS:
        raise ValueError(f"Unsupported ASYCUDA workflow: {workflow}")

    root = ET.Element("ASYCUDA")
    root.set("exportVersion", EXPORT_VERSION)
    root.set("source", SOURCE_SYSTEM)
    _export_meta(root, workflow=workflow, status=status)

    if workflow == WORKFLOW_DECLARATION:
        if not reviewed:
            raise ValueError("Declaration export requires reviewed BL / Z-SAD context.")
        _declaration_header(root, reviewed, invoice)

    _transport_document(root, bl)
    _traders(root, bl, company)
    _transport(root, bl)
    _goods(root, bl, cargo_items or [])

    if workflow == WORKFLOW_DECLARATION:
        _containers(root, containers or [], bl)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def export_filename(*, workflow: str, bl: dict, reviewed: dict | None = None) -> str:
    ref = (reviewed or {}).get("z_sad_number") if workflow == WORKFLOW_DECLARATION else bl.get("bl_number")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (ref or "draft"))
    prefix = "Clearance" if workflow == WORKFLOW_CLEARANCE else "Declaration"
    return f"ZCAMS-{prefix}-{safe}.xml"


def bl_payload_to_export_context(payload: dict, company: dict | None = None) -> dict[str, Any]:
    cargo_description = payload.get("cargo_description") or "General cargo"
    cargo_items = [
        {
            "description": cargo_description,
            "hs_code": payload.get("hs_code"),
            "quantity": payload.get("quantity") or 1,
            "unit": payload.get("gn83_unit"),
            "weight": payload.get("gross_weight"),
            "gn83_category": payload.get("gn83_category"),
            "min_fee_usd": payload.get("gn83_fee_usd"),
        }
    ]
    return {
        "bl": payload,
        "company": company,
        "cargo_items": cargo_items,
        "containers": [],
        "reviewed": None,
        "invoice": None,
    }
