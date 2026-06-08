#!/usr/bin/env python3
"""Run on the server to verify ZCAMS Chat (local model + OpenAI fallback).

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
    section("Environment")
    print("CHAT_MODEL_ENABLED:", os.getenv("CHAT_MODEL_ENABLED", "(unset)"))
    print("CHAT_MODEL_NAME:", os.getenv("CHAT_MODEL_NAME", "(unset)"))
    print("OPENAI_CHAT_MODEL:", os.getenv("OPENAI_CHAT_MODEL") or os.getenv("OPENAI_OCR_MODEL") or "(default gpt-4o-mini)")

    from services.chat_service import _resolve_openai_api_key, answer_public_visitor_question

    print("OPENAI_API_KEY usable:", bool(_resolve_openai_api_key()))

    section("Optional local model (Transformers)")
    model_enabled = os.getenv("CHAT_MODEL_ENABLED", "false").lower() == "true"
    if not model_enabled:
        print("SKIP: CHAT_MODEL_ENABLED is not true — visitor chat uses FAQ + OpenAI when configured.")
    else:
        try:
            import torch
            import transformers

            print("torch:", torch.__version__)
            print("transformers:", transformers.__version__)
            cache = Path(os.getenv("HF_HOME") or Path.home() / ".cache" / "huggingface")
            print("HF cache dir exists:", cache.is_dir())
            if cache.is_dir():
                hub = cache / "hub"
                model_name = os.getenv("CHAT_MODEL_NAME", "unsloth/Qwen2.5-0.5B-Instruct")
                slug = "models--" + model_name.replace("/", "--")
                local = hub / slug
                print("Model cache folder:", local)
                print("Model appears cached:", local.is_dir())
        except Exception as exc:
            print("Local model deps FAILED:", exc)
            traceback.print_exc()

        if model_enabled:
            section("Local model smoke test")
            try:
                from services.chat_service import _pipeline

                t0 = time.time()
                pipe = _pipeline()
                print(f"Pipeline loaded in {time.time() - t0:.1f}s")
                result = pipe("Say OK.", max_new_tokens=8, do_sample=False, return_full_text=False)
                print("Sample output:", result[0]["generated_text"][:120])
            except Exception as exc:
                print("Local model load FAILED:", exc)
                traceback.print_exc()
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

    mode = result.get("mode") or ""
    if mode in {"public-fallback", "governed"} and not _resolve_openai_api_key() and not model_enabled:
        print(
            "\nNOTE: Set OPENAI_API_KEY in .env for general-knowledge answers on EC2, "
            "or set CHAT_MODEL_ENABLED=true and cache the HuggingFace model."
        )
        return 1

    print("\nOK: ZCAMS Chat pipeline responded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
