#!/usr/bin/env python3
"""Download and warm-cache the local Qwen chat model for ZCAMS.

Usage:
  cd /root/zcmas/cfa-dash
  source .venv/bin/activate
  python scripts/download_chat_model.py

On a small EC2 without GPU, set CHAT_DEVICE_MAP=cpu in .env before running.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    model_name = os.getenv("CHAT_MODEL_NAME", "unsloth/Qwen2.5-0.5B-Instruct")
    device_map = os.getenv("CHAT_DEVICE_MAP", "auto")
    print("Model:", model_name)
    print("Device map:", device_map)
    print("Downloading and loading (first run may take several minutes)...")

    try:
        from transformers import pipeline

        t0 = time.time()
        pipe = pipeline(
            "text-generation",
            model=model_name,
            tokenizer=model_name,
            device_map=device_map,
        )
        elapsed = time.time() - t0
        print(f"Pipeline ready in {elapsed:.1f}s")

        sample = pipe("Say OK in one word.", max_new_tokens=6, do_sample=False, return_full_text=False)
        print("Smoke test output:", sample[0]["generated_text"].strip())

        from services.chat_service import clear_chat_pipeline_cache

        clear_chat_pipeline_cache()
        print("\nOK: Qwen chat model is downloaded and ready.")
        print("Ensure cfa-dash/.env has:")
        print("  CHAT_MODEL_ENABLED=true")
        print("  CHAT_MODEL_NAME=" + model_name)
        print("Then restart ZCAMS: sudo systemctl restart zcams")
        return 0
    except Exception as exc:
        print("FAILED:", exc)
        print("\nTips:")
        print("- pip install -r requirements.txt")
        print("- On CPU-only EC2: CHAT_DEVICE_MAP=cpu")
        print("- Ensure enough disk space (~2GB) and RAM (~2GB+)")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
