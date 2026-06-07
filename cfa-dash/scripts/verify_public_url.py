#!/usr/bin/env python3
"""Verify PUBLIC_APP_URL and contract signing links on EC2 or local."""

from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.repository import contract_sign_url, _public_app_base_url  # noqa: E402


def main() -> int:
    env_file = ROOT / ".env"
    print(f"env file: {env_file} ({'found' if env_file.is_file() else 'missing'})")
    print(f"PUBLIC_APP_URL env: {os.getenv('PUBLIC_APP_URL')!r}")
    print(f"public base URL:    {_public_app_base_url()!r}")

    source = inspect.getsource(_public_app_base_url)
    uses_public_app_url = "PUBLIC_APP_URL" in source
    print(f"code reads PUBLIC_APP_URL: {uses_public_app_url}")
    if not uses_public_app_url:
        print("ERROR: deployed code is outdated — git pull origin main and restart zcams.")
        return 1

    sample = contract_sign_url("contract-test", "importer@example.com")
    print(f"sample sign URL:    {sample}")
    if "127.0.0.1" in sample or "localhost" in sample.lower():
        print("ERROR: still generating localhost links — set PUBLIC_APP_URL=https://zcams.info in .env")
        return 1

    print("OK: contract links will use the public site URL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
