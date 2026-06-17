import uuid

from services.asycuda_xml import (
    WORKFLOW_CLEARANCE,
    WORKFLOW_DECLARATION,
    bl_payload_to_export_context,
    build_asycuda_xml,
    export_filename,
)
from services.repository import bootstrap, create_bl, review_bl


def test_build_clearance_xml_contains_transport_document():
    payload = {
        "bl_number": "MSC1234567890",
        "doc_type": "Bill of Lading",
        "route_type": "Import",
        "transport_mode": "Sea",
        "zra_regime": "IMPORT_HOME_USE",
        "consignee_name": "Importer Ltd",
        "consignee_tin": "1000123456",
        "origin": "Durban",
        "destination": "Lusaka",
        "gross_weight": 12000,
        "no_containers": 2,
        "cargo_description": "Motor vehicles",
        "gn83_category": "MOTOR_VEHICLE",
        "gn83_unit": "Vehicle",
        "gn83_fee_usd": 130,
    }
    context = bl_payload_to_export_context(payload, {"name": "ZAFFA Demo", "tpin": "9999999999"})
    xml = build_asycuda_xml(
        workflow=WORKFLOW_CLEARANCE,
        bl=context["bl"],
        company=context["company"],
        cargo_items=context["cargo_items"],
        status="DRAFT",
    )

    assert "<?xml version=" in xml
    assert "MSC1234567890" in xml
    assert "<DocumentType>Clearance</DocumentType>" in xml
    assert "<Status>DRAFT</Status>" in xml
    assert "Importer Ltd" in xml
    assert "<Manifest>" not in xml


def test_build_declaration_xml_includes_containers_not_manifest():
    payload = {
        "bl_number": "AWB-001",
        "doc_type": "Air Waybill",
        "route_type": "Import",
        "transport_mode": "Air",
        "zra_regime": "IMPORT_HOME_USE",
        "no_containers": 1,
        "cargo_description": "Spare parts",
        "gn83_category": "LOOSE_LCL",
    }
    context = bl_payload_to_export_context(payload)
    reviewed = {"z_sad_number": "Z-SAD-0001-ABCDEF", "status": "REVIEWED_ZSAD_ISSUED", "bl_number": "AWB-001"}
    xml = build_asycuda_xml(
        workflow=WORKFLOW_DECLARATION,
        bl=context["bl"],
        cargo_items=context["cargo_items"],
        containers=[],
        reviewed=reviewed,
        status="DRAFT",
    )

    assert "<DocumentType>Declaration</DocumentType>" in xml
    assert "<Containers>" in xml
    assert "<Manifest>" not in xml


def test_build_declaration_xml_from_repository():
    bootstrap()
    suffix = uuid.uuid4().hex[:8].upper()
    bl = create_bl(
        {
            "bl_number": f"DECL-XML-{suffix}",
            "doc_type": "Bill of Lading",
            "route_type": "Import",
            "transport_mode": "Sea",
            "zra_regime": "IMPORT_HOME_USE",
            "consignee_name": "Consignee",
            "consignee_tin": "1000123456",
            "cargo_description": "General cargo",
            "gn83_category": "MOTOR_VEHICLE",
            "gn83_unit": "Vehicle",
            "gn83_fee_usd": 130,
            "no_containers": 1,
            "gross_weight": 5000,
        },
        auto_review=False,
    )
    reviewed = review_bl(bl["id"])
    from services.repository import asycuda_export_context_for_declaration

    context = asycuda_export_context_for_declaration(reviewed["id"])
    xml = build_asycuda_xml(
        workflow=WORKFLOW_DECLARATION,
        bl=context["bl"],
        company=context["company"],
        cargo_items=context["cargo_items"],
        containers=context["containers"],
        reviewed=context["reviewed"],
        invoice=context["invoice"],
        status="DRAFT",
    )

    assert reviewed["z_sad_number"] in xml
    assert "<DocumentType>Declaration</DocumentType>" in xml
    assert "DECL-XML-" in xml


def test_export_filename_sanitizes_reference():
    name = export_filename(workflow=WORKFLOW_CLEARANCE, bl={"bl_number": "BL/001*test"})
    assert name.endswith(".xml")
    assert "/" not in name
    assert "*" not in name
    assert name.startswith("ZCAMS-Clearance-")
