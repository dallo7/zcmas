"""Auth sessions and role-based access tests."""

from services import auth, repository


def test_normalize_role_maps_agent_to_declarant():
    assert repository.normalize_role("AGENT") == auth.ROLE_DECLARANT
    assert auth.role_label("DECLARANT") == "Declarant / Agent"


def test_path_allowed_by_role():
    assert auth.path_allowed(auth.ROLE_SUPER_ADMIN, "/super-admin")
    assert auth.path_allowed(auth.ROLE_COMPANY_ADMIN, "/admin")
    assert auth.path_allowed(auth.ROLE_COMPANY_ADMIN, "/company-profile")
    assert not auth.path_allowed(auth.ROLE_DECLARANT, "/company-profile")
    assert not auth.path_allowed(auth.ROLE_DECLARANT, "/admin")
    assert auth.path_allowed(auth.ROLE_DECLARANT, "/bls")
    assert auth.path_allowed(auth.ROLE_DECLARANT, "/reviewed-bl")


def test_default_home_by_role():
    assert auth.default_home(auth.ROLE_SUPER_ADMIN) == "/super-admin"
    assert auth.default_home(auth.ROLE_COMPANY_ADMIN) == "/dashboard"
    assert auth.default_home(auth.ROLE_DECLARANT) == "/dashboard"


def test_super_admin_nav_has_operations_without_support_modules():
    from components.layout import nav_items_for_user

    primary, admin, secondary = nav_items_for_user({"role": auth.ROLE_SUPER_ADMIN})
    primary_paths = [item[0].split("#", 1)[0] for item in primary]
    secondary_paths = [item[0] for item in secondary]

    assert "/dashboard" in primary_paths
    assert "/bls" in primary_paths
    assert "/reviewed-bl" in primary_paths
    assert "/admin" in [item[0] for item in admin]
    assert "/notifications" not in secondary_paths
    assert "/support" not in secondary_paths
    assert "/chat" in secondary_paths


def test_session_create_and_resolve(app_ctx):
    user = repository.authenticate_user("superadmin", "demo123")
    assert user
    token = auth.create_session(user)
    assert token
    resolved = auth.resolve_session_user(token)
    assert resolved
    assert resolved["email"] == user["email"]
    auth.revoke_session(token)
    assert auth.resolve_session_user(token) is None


def test_demo_agent_is_declarant():
    repository.ensure_demo_users()
    user = repository.authenticate_user("agent", "demo123")
    assert user
    assert user["role"] == auth.ROLE_DECLARANT
