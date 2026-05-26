from __future__ import annotations

import os

import requests


class BackendApiClient:
    """Optional wrapper for keeping parity with the Django API during migration."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000/api")).rstrip("/")
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})

    def get(self, path: str, **params):
        response = self.session.get(f"{self.base_url}/{path.lstrip('/')}", params=params, timeout=20)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, payload: dict):
        response = self.session.post(f"{self.base_url}/{path.lstrip('/')}", json=payload, timeout=20)
        response.raise_for_status()
        return response.json()
