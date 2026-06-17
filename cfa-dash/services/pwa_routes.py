"""Progressive Web App routes: manifest, service worker, and offline shell."""

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Response, abort, send_file

APP_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = APP_ROOT / "assets"
DEFAULT_THEME_COLOR = "#0a4f20"
DEFAULT_BACKGROUND_COLOR = "#062d13"


def pwa_enabled() -> bool:
    return os.getenv("PWA_ENABLED", "true").strip().lower() not in {"false", "0", "no", "off"}


def pwa_start_url() -> str:
    configured = (os.getenv("PWA_START_URL") or "/login").strip()
    return configured if configured.startswith("/") else f"/{configured}"


def build_manifest(*, start_url: str | None = None) -> dict:
    start = start_url or pwa_start_url()
    theme = (os.getenv("PWA_THEME_COLOR") or DEFAULT_THEME_COLOR).strip()
    background = (os.getenv("PWA_BACKGROUND_COLOR") or DEFAULT_BACKGROUND_COLOR).strip()
    icon = (os.getenv("PWA_ICON_PATH") or "/assets/zcams-logo.png").strip()
    return {
        "name": "ZCAMS — Zambia Clearing Agent Management System",
        "short_name": "ZCAMS",
        "description": (
            "Zambia customs agent management for CFAs: BL capture, Z-SAD, GN 83 invoicing, and Check-out."
        ),
        "start_url": start,
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": background,
        "theme_color": theme,
        "icons": [
            {
                "src": icon,
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": icon,
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
        "categories": ["business", "finance", "productivity"],
    }


def register_pwa_routes(flask_app) -> None:
    @flask_app.get("/manifest.webmanifest")
    def manifest():
        if not pwa_enabled():
            abort(404)
        body = json.dumps(build_manifest(), indent=2)
        return Response(body, mimetype="application/manifest+json")

    @flask_app.get("/sw.js")
    def service_worker():
        if not pwa_enabled():
            abort(404)
        sw_path = ASSETS_DIR / "sw.js"
        if not sw_path.is_file():
            abort(404)
        response = send_file(sw_path, mimetype="application/javascript")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @flask_app.get("/offline")
    def offline_page():
        if not pwa_enabled():
            abort(404)
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#0a4f20">
  <title>ZCAMS — Offline</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: "Segoe UI", system-ui, sans-serif;
      color: #fff;
      background: linear-gradient(135deg, #062d13 0%, #0a4f20 48%, #198a00 100%);
      padding: 24px;
      text-align: center;
    }
    .card {
      max-width: 420px;
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 16px;
      padding: 28px 24px;
    }
    h1 { margin: 0 0 12px; font-size: 1.4rem; }
    p { margin: 0 0 18px; line-height: 1.5; opacity: 0.92; }
    button {
      border: 0;
      border-radius: 999px;
      padding: 10px 18px;
      font-weight: 600;
      cursor: pointer;
      background: #f5b700;
      color: #062d13;
    }
  </style>
</head>
<body>
  <div class="card">
    <h1>You are offline</h1>
    <p>ZCAMS needs a network connection for live BL, invoice, and Check-out workflows. Reconnect and try again.</p>
    <button type="button" onclick="location.reload()">Retry</button>
  </div>
</body>
</html>"""
        return Response(html, mimetype="text/html; charset=utf-8")
