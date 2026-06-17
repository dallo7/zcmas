import uuid

from services.repository import bootstrap, create_bl, review_bl


def test_asycuda_download_routes_require_auth():
    import app as zapp

    client = zapp.server.test_client()
    assert client.get("/download/asycuda/clearance/bl/missing.xml").status_code == 401
    assert client.get("/download/asycuda/declaration/missing.xml").status_code == 401


def test_asycuda_download_routes_serve_xml():
    bootstrap()
    suffix = uuid.uuid4().hex[:8].upper()
    bl = create_bl(
        {
            "bl_number": f"ROUTE-XML-{suffix}",
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

    from services.auth import install_client_session

    import app as zapp

    client = zapp.server.test_client()
    install_client_session(
        client,
        {"id": "user-admin-demo", "role": "ADMIN", "company_id": "company-zaffa-demo"},
    )

    clearance = client.get(f"/download/asycuda/clearance/bl/{bl['id']}.xml")
    declaration = client.get(f"/download/asycuda/declaration/{reviewed['id']}.xml")

    assert clearance.status_code == 200
    assert suffix.encode() in clearance.data
    assert b"Clearance" in clearance.data
    assert b"Manifest" not in clearance.data

    assert declaration.status_code == 200
    assert reviewed["z_sad_number"].encode() in declaration.data
    assert b"Declaration" in declaration.data
