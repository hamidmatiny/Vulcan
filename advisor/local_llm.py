"""Local synthesis via pinned reference-tiny-llm (GPT-2-small) — ADR-014."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def models_dir() -> Path:
    env = os.environ.get("VULCAN_MODELS_DIR")
    if env:
        return Path(env)
    return repo_root() / "models" / "artifacts"


def gpt2_path() -> Path:
    return models_dir() / "llm" / "gpt2-small"


def local_llm_available() -> bool:
    p = gpt2_path()
    return (p / "config.json").is_file() and (
        (p / "model.safetensors").is_file() or (p / "pytorch_model.bin").is_file()
    )


def generate_commentary(prompt: str, *, max_new_tokens: int = 24) -> dict[str, Any]:
    """Run a tiny CPU generate on the pinned model. Quality is not the CI bar."""
    if not local_llm_available():
        return {
            "ok": False,
            "text": "",
            "reason": f"pinned model missing under {gpt2_path()} (run make models-export)",
        }
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    path = str(gpt2_path())
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True)
    model.eval()
    device = "cpu"
    model.to(device)
    inputs = tokenizer(prompt, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    prompt_len = int(inputs["input_ids"].shape[-1])
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max(1, int(max_new_tokens)),
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    text = tokenizer.decode(out[0][prompt_len:], skip_special_tokens=True).strip()
    return {
        "ok": True,
        "text": text,
        "model_id": "reference-tiny-llm",
        "path": path,
        "usage": {
            "prompt_tokens": prompt_len,
            "completion_tokens": int(out[0].shape[0] - prompt_len),
        },
    }
