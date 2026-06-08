#!/usr/bin/env python3
"""Run on the server to verify ZCAMS Chat local Qwen model.

Usage:
  cd /root/zcmas/cfa-dash
  source .venv/bin/activate
  python scripts/diagnose_chat.py
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    from services.chat_service import _chat_model_enabled, answer_public_visitor_question

    section("Environment")
    print("CHAT_MODEL_ENABLED env:", os.getenv("CHAT_MODEL_ENABLED", "(unset, defaults true)"))
    print("Effective chat model enabled:", _chat_model_enabled())
    print("CHAT_MODEL_NAME:", os.getenv("CHAT_MODEL_NAME", "(unset)"))
    print("CHAT_DEVICE_MAP:", os.getenv("CHAT_DEVICE_MAP", "auto"))

    if not _chat_model_enabled():
        print("\nERROR: Chat model disabled. Set CHAT_MODEL_ENABLED=true in .env")
        return 1

    section("Dependencies")
    try:
        import torch
        import transformers

        print("torch:", torch.__version__)
        print("transformers:", transformers.__version__)
        print("cuda available:", torch.cuda.is_available())
    except Exception as exc:
        print("Import FAILED:", exc)
        traceback.print_exc()
        return 1

    section("Model cache")
    cache = Path(os.getenv("HF_HOME") or Path.home() / ".cache" / "huggingface")
    model_name = os.getenv("CHAT_MODEL_NAME", "unsloth/Qwen2.5-0.5B-Instruct")
    slug = "models--" + model_name.replace("/", "--")
    local = cache / "hub" / slug
    print("HF cache:", cache)
    print("Expected model folder:", local)
    print("Model appears cached:", local.is_dir())
    if not local.is_dir():
        print("Run: python scripts/download_chat_model.py")

    section("Local model smoke test")
    try:
        from services.chat_service import _pipeline

        t0 = time.time()
        pipe = _pipeline()
        print(f"Pipeline loaded in {time.time() - t0:.1f}s")
        result = pipe("Reply with one word: OK", max_new_tokens=8, do_sample=False, return_full_text=False)
        print("Sample output:", result[0]["generated_text"][:120])
    except Exception as exc:
        print("Local model FAILED:", exc)
        traceback.print_exc()
        print("\nRun: python scripts/download_chat_model.py")
        return 1

    section("Public visitor chat sample")
    sample = "What documents does an importer need for customs clearance in Zambia?"
    try:
        t0 = time.time()
        result = answer_public_visitor_question(sample)
        print(f"mode={result.get('mode')} elapsed={time.time() - t0:.1f}s")
        print("answer preview:", (result.get("answer") or "")[:500])
    except Exception as exc:
        print("Public chat FAILED:", exc)
        traceback.print_exc()
        return 1

    if result.get("mode") == "public-fallback":
        print("\nWARN: Got generic fallback — FAQ did not match and local model may have failed silently.")
        return 1

    print("\nOK: ZCAMS Chat Qwen pipeline responded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
