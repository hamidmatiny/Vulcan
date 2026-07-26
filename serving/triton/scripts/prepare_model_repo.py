#!/usr/bin/env python3
"""Populate Triton model_repository with ONNX from phase-1 pinned artifacts.

Vision: copy ResNet-18 ONNX (byte-identical to models/MANIFEST.md).
LLM: export GPT-2 safetensors → ONNX (weights sourced from the same pin).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "models" / "artifacts"
REPO = ROOT / "serving" / "triton" / "model_repository"


def prepare_vision() -> Path:
    src = ARTIFACTS / "vision" / "resnet18" / "model.onnx"
    if not src.is_file():
        raise SystemExit(f"missing {src} — run make models-export first")
    dest_dir = REPO / "reference_tiny_vision" / "1"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "model.onnx"
    shutil.copy2(src, dest)
    print(f"vision: {src} → {dest}")
    return dest


def prepare_llm() -> Path:
    src_dir = ARTIFACTS / "llm" / "gpt2-small"
    if not (src_dir / "model.safetensors").is_file() and not (src_dir / "config.json").is_file():
        raise SystemExit(f"missing LLM artifacts under {src_dir} — run make models-export first")

    dest_dir = REPO / "reference_tiny_llm" / "1"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "model.onnx"
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        print(f"llm: reusing existing {dest}")
        return dest

    import torch
    from transformers import AutoModelForCausalLM

    print(f"llm: exporting ONNX from {src_dir} …", flush=True)
    model = AutoModelForCausalLM.from_pretrained(str(src_dir), local_files_only=True)
    model.eval()

    class Gpt2Onnx(torch.nn.Module):
        def __init__(self, m: torch.nn.Module) -> None:
            super().__init__()
            self.m = m

        def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
            return self.m(input_ids=input_ids, attention_mask=attention_mask).logits

    wrapper = Gpt2Onnx(model)
    seq = 8
    input_ids = torch.ones(1, seq, dtype=torch.long)
    attention_mask = torch.ones(1, seq, dtype=torch.long)
    torch.onnx.export(
        wrapper,
        (input_ids, attention_mask),
        str(dest),
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "sequence"},
            "attention_mask": {0: "batch", 1: "sequence"},
            "logits": {0: "batch", 1: "sequence"},
        },
        opset_version=17,
        do_constant_folding=True,
    )
    meta = {
        "source_artifact": "models/artifacts/llm/gpt2-small",
        "format": "onnx",
        "opset": 17,
        "inputs": ["input_ids", "attention_mask"],
        "outputs": ["logits"],
        "vocab_size": 50257,
    }
    (dest_dir / "export-meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"llm: wrote {dest} ({dest.stat().st_size} bytes)")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm-only", action="store_true")
    parser.add_argument("--vision-only", action="store_true")
    args = parser.parse_args()
    if not args.llm_only:
        prepare_vision()
    if not args.vision_only:
        prepare_llm()
    print("OK: Triton model_repository ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
