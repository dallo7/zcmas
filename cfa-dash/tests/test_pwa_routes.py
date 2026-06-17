from services.pwa_routes import build_manifest, pwa_enabled, register_pwa_routes


def test_build_manifest_has_required_pwa_fields():
    manifest = build_manifest(start_url="/login")

    assert manifest["short_name"] == "ZCAMS"
    assert manifest["start_url"] == "/login"
    assert manifest["display"] == "standalone"
    assert len(manifest["icons"]) >= 2


def test_pwa_routes_served_when_enabled(monkeypatch):
    monkeypatch.setenv("PWA_ENABLED", "true")

    import app as zapp

    client = zapp.server.test_client()
    manifest = client.get("/manifest.webmanifest")
    sw = client.get("/sw.js")
    offline = client.get("/offline")

    assert manifest.status_code == 200
    assert "application/manifest" in (manifest.content_type or "")
    assert b"ZCAMS" in manifest.data

    assert sw.status_code == 200
    assert b"service worker" in sw.data.lower() or b"zcams-pwa" in sw.data.lower()

    assert offline.status_code == 200
    assert b"You are offline" in offline.data


def test_pwa_routes_hidden_when_disabled(monkeypatch):
    monkeypatch.setenv("PWA_ENABLED", "false")

    import app as zapp

    client = zapp.server.test_client()
    assert client.get("/manifest.webmanifest").status_code == 404
    assert client.get("/sw.js").status_code == 404


def test_pwa_enabled_defaults_true(monkeypatch):
    monkeypatch.delenv("PWA_ENABLED", raising=False)
    assert pwa_enabled() is True
