from pathlib import Path


def test_bl_upload_runs_ocr_once_without_interval(monkeypatch, tmp_path):
    import app  # noqa: F401
    from pages import bls
    from services import repository

    saved_path = tmp_path / "uploaded.pdf"
    calls = []

    def fake_save(_contents, _filename):
        saved_path.write_bytes(b"%PDF tutorial")
        return saved_path

    def fake_extract(path):
        calls.append(path)
        return {
            "bl_number": "BL-FAST-001",
            "bl_type": "IM4",
            "currency": "USD",
            "doc_type": "Bill of Lading",
            "route_type": "Import",
            "transport_mode": "Sea",
            "zra_regime": "IM4 Home Use",
            "consignee_name": "Fast Importer",
            "company_name": "Fast Importer",
            "consignee_tin": "1000123456",
            "consignor_tin": "SHIPPER-001",
            "agent_license": "ZRA-AGT-2026-001",
            "declarant_number": "ZRA-AGT-2026-001",
            "consignment_value": 54130,
            "origin": "Durban",
            "destination": "Lusaka",
            "no_containers": 1,
            "gross_weight": 12.5,
            "cargo_description": "Tutorial cargo",
            "gn83_category": "MOTOR_VEHICLE",
            "gn83_unit": "Unit",
            "gn83_fee_usd": 130,
            "ocr_provider": "pypdf",
            "ocr_mode": "text_pdf",
        }

    monkeypatch.setattr(bls, "save_uploaded_bl", fake_save)
    monkeypatch.setattr(bls.ocr, "extract_bl_fields", fake_extract)

    outputs = bls.queue_bl_upload("data:application/pdf;base64,AAAA", "uploaded.pdf")

    assert calls == [str(saved_path)]
    assert len(outputs) == 28
    assert outputs[1] is True
    assert outputs[2] == 0
    assert outputs[6] == {"path": str(saved_path), "filename": "uploaded.pdf"}
    assert outputs[7]["bl_number"] == "BL-FAST-001"
    assert outputs[7]["bl_type"] == "IM4"
    assert outputs[7]["currency"] == "USD"
    assert outputs[8] == "BL-FAST-001"
    company = repository.get_company(repository.DEMO_COMPANY_ID)
    assert outputs[14] == company["name"]
    assert outputs[16] == "SHIPPER-001"
    assert outputs[17] == "ZRA-AGT-2026-001"
    assert outputs[18] == company["tpin"]
    assert outputs[25] == "MOTOR_VEHICLE"
    assert outputs[26] == "Unit"
    assert outputs[27] == 130


def test_bl_upload_error_shape_disables_interval(monkeypatch):
    import app  # noqa: F401
    from pages import bls

    monkeypatch.setattr(bls, "save_uploaded_bl", lambda *_args: Path("bad.pdf"))
    monkeypatch.setattr(bls.ocr, "extract_bl_fields", lambda _path: (_ for _ in ()).throw(ValueError("OCR failed")))

    outputs = bls.queue_bl_upload("data:application/pdf;base64,AAAA", "uploaded.pdf")

    assert len(outputs) == 28
    assert outputs[0] is None
    assert outputs[1] is True
    assert outputs[2] == 0
    assert outputs[6] is None
    assert outputs[7] is None
