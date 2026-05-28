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


def test_app_shell_places_sidebar_before_main_content():
    import app as zapp

    app_root = next(child for child in zapp.app.layout.children if getattr(child, "id", None) == "app-root")
    children = app_root.children
    assert children[0].id == "sidebar-slot"
    assert children[1].id == "main-stack"
    assert children[1].children[0].id == "super-admin-banner-slot"
    assert children[1].children[1].id == "workflow-strip-slot"
    assert children[1].children[2].id == "page-slot"


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


def test_render_page_super_admin_on_auth_user_trigger():
    import app as zapp

    from dash import no_update

    user = {"role": "SUPER_ADMIN", "email": "superadmin@zcams.co.zm"}
    with patch.object(zapp, "_callback_trigger", return_value="auth-user"):
        children, pathname = zapp.render_page("/super-admin", user)
    assert pathname is no_update
    rendered = str(children)
    assert "Platform Control Centre" in rendered or "CFA Registry" in rendered


def test_render_page_admin_for_company_admin():
    import app as zapp

    from dash import no_update
    from services.repository import DEMO_COMPANY_ID

    user = {"role": "COMPANY_ADMIN", "email": "admin@demo.test", "company_id": DEMO_COMPANY_ID}
    with patch.object(zapp, "_callback_trigger", return_value="auth-user"):
        children, pathname = zapp.render_page("/admin", user)
    assert pathname is no_update
    rendered = str(children)
    assert "Company Administration" in rendered
    assert "Access Control" in rendered
    assert "Operational Oversight" in rendered


def test_render_page_forces_password_change_before_workspace():
    import app as zapp

    from services.repository import DEMO_COMPANY_ID

    user = {
        "role": "DECLARANT",
        "email": "declarant@demo.test",
        "company_id": DEMO_COMPANY_ID,
        "must_change_password": True,
    }
    children, pathname = zapp.render_page("/dashboard", user)
    assert pathname == "/change-password"
    assert "Set Your ZCAMS Password" in str(children)


def test_render_page_blocks_admin_for_declarant():
    import app as zapp

    from services.repository import DEMO_COMPANY_ID

    user = {"role": "DECLARANT", "email": "declarant@demo.test", "company_id": DEMO_COMPANY_ID}
    children, pathname = zapp.render_page("/admin", user)
    assert pathname == "/dashboard"
    assert children is not None


def test_super_admin_chrome_uses_dedicated_shell_without_workflow():
    import app as zapp

    user = {
        "role": "SUPER_ADMIN",
        "email": "superadmin@zcams.co.zm",
        "first_name": "Super",
        "last_name": "Admin",
    }
    sidebar, banner, workflow, app_class, root_class = zapp.render_app_chrome("/super-admin", user, "light")
    assert sidebar is not None
    assert banner is not None
    assert workflow is None
    assert "app-shell" in app_class
    assert "super-admin-shell" in app_class
    assert root_class == "theme-light"


def test_render_page_redirects_authenticated_login_to_role_home():
    import app as zapp

    from dash import no_update

    user = {"role": "SUPER_ADMIN", "email": "superadmin@zcams.co.zm"}
    with patch.object(zapp, "_callback_trigger", return_value="auth-user"):
        children, pathname = zapp.render_page("/login", user)
    assert children is no_update
    assert pathname == "/super-admin"


def test_render_page_logout_clears_session_and_shows_login():
    import app as zapp

    user = {"role": "COMPANY_ADMIN", "email": "admin@demo.test"}
    with patch.object(zapp.auth, "logout_current_session") as mock_logout:
        children, pathname = zapp.render_page("/logout", user)
    assert pathname == "/login"
    assert "Agent Sign In" in str(children) or "public-page" in str(children)
    mock_logout.assert_called_once()


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
