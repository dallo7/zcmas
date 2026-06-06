def test_bl_capture_gn83_fee_recalculates_for_containers():
    import app  # noqa: F401
    from pages import bls

    unit, fee = bls._gn83_dynamic_values("Import", "Sea", "20FT_CONTAINER", 3, 200)

    assert unit == "Container"
    assert fee == 450


def test_asycuda_gn83_fee_recalculates_for_bulk_weight():
    import app  # noqa: F401
    from pages import reviewed_bl

    unit, fee = reviewed_bl._gn83_dynamic_values("Import", "Sea", "BULK_LIQUID", 0, 200)

    assert unit == "MT"
    assert fee == 120


def test_gn83_fee_recalculates_when_product_changes_to_fixed_unit():
    import app  # noqa: F401
    from pages import reviewed_bl

    unit, fee = reviewed_bl._gn83_dynamic_values("Import", "Sea", "MOTOR_VEHICLE", 3, 200)

    assert unit == "Unit"
    assert fee == 390
