#!/usr/bin/env python3
"""Structural lint for Triton's tensorrt_llm config.pbtxt template (no engine build)."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def validate(text: str, path: Path) -> list[str]:
    errors: list[str] = []
    if not re.search(r'(?m)^name:\s*"[^"]+"', text):
        errors.append(f"{path}: missing name: \"...\"")
    if not re.search(r'(?m)^backend:\s*"tensorrt_llm"', text):
        errors.append(f"{path}: backend must be \"tensorrt_llm\"")
    if "KIND_GPU" not in text:
        errors.append(f"{path}: expected instance_group with KIND_GPU")
    if re.search(r"kind:\s*KIND_CPU", text) and "KIND_GPU" not in text:
        errors.append(f"{path}: CPU-only instance_group is invalid for TensorRT-LLM template")
    if "model_transaction_policy" not in text or "decoupled" not in text:
        errors.append(f"{path}: expected model_transaction_policy {{ decoupled: ... }}")
    if "max_batch_size" not in text:
        errors.append(f"{path}: missing max_batch_size")
    if "gpt_model_path" not in text:
        errors.append(f"{path}: expected parameters key gpt_model_path")
    if "gpt_model_type" not in text:
        errors.append(f"{path}: expected parameters key gpt_model_type")
    # Forbid accidental ONNX CPU platform in this template.
    if re.search(r'platform:\s*"onnxruntime', text):
        errors.append(f"{path}: onnxruntime platform must not appear in TensorRT-LLM template")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    path = root / "model_repository" / "reference_tiny_llm_trtllm" / "config.pbtxt"
    if not path.is_file():
        print(f"FAIL: missing {path}", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")
    errors = validate(text, path)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(f"OK: structural lint passed for {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
