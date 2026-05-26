"""Smoke tests for app shell routing (blank-page regression guard)."""

from unittest.mock import patch


def test_layout_uses_explicit_page_slot():
    import app as zapp

    layout_repr = str(zapp.app.layout)
    assert "_pages_location" in layout_repr
    assert "page-slot" in layout_repr
    assert "page_container" not in layout_repr
    assert "zcams-modal-layer" in layout_repr
    assert "invoice-request-modal" in layout_repr
    assert "invoice-pick-service" in layout_repr


def test_render_page_redirects_root_to_login():
    import app as zapp
    from dash import no_update

    children, pathname = zapp.render_page("/", None)
    assert children is no_update
    assert pathname == "/login"


def test_render_page_shows_login_layout():
    import app as zapp

    from dash import no_update

    with patch.object(zapp, "_callback_trigger", return_value="_pages_location"):
        children, pathname = zapp.render_page("/login", None)
    assert pathname is no_update
    rendered = str(children)
    assert "Agent Sign In" in rendered or "public-page" in rendered


def test_render_page_blocks_dashboard_without_user():
    import app as zapp

    children, pathname = zapp.render_page("/dashboard", None)
    assert pathname == "/login"
    rendered = str(children)
    assert "Agent Sign In" in rendered or "public-page" in rendered


def test_render_page_skips_rebuild_on_auth_user_for_login():
    import app as zapp

    from dash import no_update

    with patch.object(zapp, "_callback_trigger", return_value="auth-user"):
        children, pathname = zapp.render_page("/login", None)
    assert children is no_update
    assert pathname is no_update


def test_invoice_modal_opens_from_store_payload():
    from unittest.mock import patch

    from pages import reviewed_bl
    from services import repository

    reviewed = repository.list_reviewed_bls()
    assert reviewed, "seed data should include at least one reviewed BL"
    rid = reviewed[0]["id"]

    with patch.object(reviewed_bl, "ctx") as mock_ctx:
        mock_ctx.triggered = [{"prop_id": "invoice-request", "value": 1}]
        mock_ctx.triggered_id = {"type": "invoice-request", "id": rid, "variant": "choose"}
        choose = reviewed_bl.toggle_invoice_modal([1], None, None, None, None, None)[:19]
        mock_ctx.triggered_id = {"type": "invoice-request", "id": rid, "variant": "service"}
        service = reviewed_bl.toggle_invoice_modal([1], None, None, None, None, None)[:19]
        mock_ctx.triggered_id = {"type": "invoice-request", "id": rid, "variant": "full"}
        full = reviewed_bl.toggle_invoice_modal([1], None, None, None, None, None)[:19]

    assert choose[1] == "modal-backdrop"
    assert choose[3] == "choose"
    assert service[3] == "details"
    assert service[7] == "SERVICE_FEE_ONLY"
    assert full[7] == "FULL_SETTLEMENT"
    assert choose[0]["id"] == rid
