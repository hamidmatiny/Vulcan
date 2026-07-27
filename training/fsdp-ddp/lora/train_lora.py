#!/usr/bin/env python3
"""LoRA / PEFT fine-tune on pinned reference-tiny-llm (ADR-011).

CPU-only. Writes adapter_model.safetensors + adapter_config.json and a
schema-valid LoraFineTuneResult. Adapter weights are verified structurally
(rank/shape, load, logits delta) — never SHA256-pinned (ADR-009).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "contracts" / "training-job-contract" / "src"))

os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import torch  # noqa: E402
from peft import LoraConfig, PeftModel, get_peft_model  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

from vulcan_training_contract.validate import (  # noqa: E402
    validate_lora_fine_tune_result,
    validate_lora_fine_tune_spec,
)

# Structural proof that the adapter is not a no-op (not a quality claim).
MIN_LOGITS_DELTA_L1 = 1e-4
MAX_FINAL_LOSS = 50.0
SERVED_MODEL_ID = "reference-tiny-llm-lora-demo"
BASE_MODEL_ID = "reference-tiny-llm"
FIXED_PROMPT = "user: vulcan lora probe\nassistant:"


def models_dir() -> Path:
    env = os.environ.get("VULCAN_MODELS_DIR")
    if env:
        return Path(env)
    return ROOT / "models" / "artifacts"


def base_llm_path() -> Path:
    return models_dir() / "llm" / "gpt2-small"


def default_spec(output_dir: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "job_type": "lora_finetune",
        "backend": "fsdp-ddp",
        "base_model_id": BASE_MODEL_ID,
        "served_model_id": SERVED_MODEL_ID,
        "dataset": {"kind": "synthetic_tokens", "num_samples": 32, "seq_len": 16},
        "lora": {
            "r": 4,
            "lora_alpha": 8,
            "target_modules": ["c_attn"],
            "lora_dropout": 0.0,
        },
        "hyperparameters": {
            "max_steps": 4,
            "batch_size": 2,
            "learning_rate": 1e-3,
            "seed": 0,
        },
        "cpu_dev_mode": True,
        "output_dir": output_dir,
    }


def seed_everything(seed: int) -> None:
    torch.manual_seed(seed)
    torch.set_num_threads(1)


def mean_abs_logits_delta(
    base: torch.nn.Module,
    adapted: torch.nn.Module,
    tokenizer: Any,
    device: torch.device,
) -> float:
    """Mean |logits_lora − logits_base| on a fixed prompt (structural proof)."""
    inputs = tokenizer(FIXED_PROMPT, return_tensors="pt")
    input_ids = inputs["input_ids"].to(device)
    base.eval()
    adapted.eval()
    with torch.no_grad():
        base_logits = base(input_ids=input_ids).logits
        lora_logits = adapted(input_ids=input_ids).logits
    return float((lora_logits - base_logits).abs().mean().item())


def verify_adapter_structure(adapter_dir: Path, expected_r: int, expected_alpha: int) -> dict[str, Any]:
    cfg_path = adapter_dir / "adapter_config.json"
    weights_path = adapter_dir / "adapter_model.safetensors"
    if not cfg_path.is_file():
        raise FileNotFoundError(f"missing {cfg_path}")
    if not weights_path.is_file():
        raise FileNotFoundError(f"missing {weights_path}")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    r = int(cfg.get("r") or cfg.get("lora_r") or 0)
    alpha = int(cfg.get("lora_alpha") or 0)
    if r != expected_r:
        raise RuntimeError(f"adapter rank mismatch: got {r}, expected {expected_r}")
    if alpha != expected_alpha:
        raise RuntimeError(f"adapter alpha mismatch: got {alpha}, expected {expected_alpha}")
    return cfg


def run(spec: dict[str, Any]) -> dict[str, Any]:
    validate_lora_fine_tune_spec(spec)
    out = Path(spec["output_dir"])
    adapter_dir = out / "adapter"
    out.mkdir(parents=True, exist_ok=True)
    adapter_dir.mkdir(parents=True, exist_ok=True)

    base_path = base_llm_path()
    if not (base_path / "config.json").is_file():
        raise FileNotFoundError(
            f"Base LLM missing at {base_path}. Run `make models-export` first."
        )

    hp = spec["hyperparameters"]
    lora = spec["lora"]
    seed_everything(int(hp.get("seed", 0)))
    device = torch.device("cpu")

    tokenizer = AutoTokenizer.from_pretrained(str(base_path), local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(str(base_path), local_files_only=True)
    base_model.to(device)
    base_model.eval()

    # Fresh trainable copy for PEFT (keep base frozen for delta measurement).
    train_model = AutoModelForCausalLM.from_pretrained(str(base_path), local_files_only=True)
    train_model.to(device)
    peft_config = LoraConfig(
        r=int(lora["r"]),
        lora_alpha=int(lora["lora_alpha"]),
        lora_dropout=float(lora["lora_dropout"]),
        target_modules=list(lora["target_modules"]),
        bias="none",
        task_type="CAUSAL_LM",
        fan_in_fan_out=True,  # GPT-2 c_attn is Conv1D
    )
    peft_model = get_peft_model(train_model, peft_config)
    peft_model.train()
    optimizer = torch.optim.AdamW(
        (p for p in peft_model.parameters() if p.requires_grad),
        lr=float(hp["learning_rate"]),
    )

    seq_len = int(spec["dataset"]["seq_len"])
    batch_size = int(hp["batch_size"])
    max_steps = int(hp["max_steps"])
    vocab = tokenizer.vocab_size
    loss_curve: list[dict[str, float | int]] = []
    t0 = time.perf_counter()
    final_loss = 0.0

    for step in range(1, max_steps + 1):
        input_ids = torch.randint(0, vocab, (batch_size, seq_len), device=device)
        labels = input_ids.clone()
        out_logits = peft_model(input_ids=input_ids, labels=labels)
        loss = out_logits.loss
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        final_loss = float(loss.detach().cpu())
        loss_curve.append({"step": step, "loss": final_loss})

    wall = time.perf_counter() - t0
    peft_model.save_pretrained(str(adapter_dir))
    # Ensure canonical filenames exist (peft writes these by default).
    verify_adapter_structure(adapter_dir, int(lora["r"]), int(lora["lora_alpha"]))

    # Reload adapter onto a fresh base for the logits delta proof.
    reload_base = AutoModelForCausalLM.from_pretrained(str(base_path), local_files_only=True)
    reload_base.to(device)
    adapted = PeftModel.from_pretrained(reload_base, str(adapter_dir))
    adapted.to(device)
    delta = mean_abs_logits_delta(base_model, adapted, tokenizer, device)
    if delta < MIN_LOGITS_DELTA_L1:
        raise RuntimeError(
            f"logits_delta_l1={delta} < {MIN_LOGITS_DELTA_L1}: adapter appears to be a no-op"
        )
    if final_loss > MAX_FINAL_LOSS:
        raise RuntimeError(f"final_loss too high: {final_loss}")

    result: dict[str, Any] = {
        "schema_version": 1,
        "job_type": "lora_finetune",
        "backend": "fsdp-ddp",
        "base_model_id": BASE_MODEL_ID,
        "served_model_id": SERVED_MODEL_ID,
        "status": "completed",
        "adapter_dir": str(adapter_dir),
        "adapter_files": {
            "adapter_config": "adapter_config.json",
            "adapter_weights": "adapter_model.safetensors",
        },
        "lora": {
            "r": int(lora["r"]),
            "lora_alpha": int(lora["lora_alpha"]),
            "target_modules": list(lora["target_modules"]),
        },
        "metrics": {
            "loss_curve": loss_curve,
            "final_loss": final_loss,
            "steps_completed": max_steps,
            "wall_clock_seconds": wall,
            "logits_delta_l1": delta,
        },
        "cpu_dev_mode": True,
        "verification": "structural_not_sha256",
    }
    validate_lora_fine_tune_result(result)
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (out / "metrics.json").write_text(
        json.dumps(result["metrics"], indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("training/results/lora-demo"),
    )
    args = parser.parse_args()
    if args.spec:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    else:
        spec = default_spec(str(args.output_dir))
    result = run(spec)
    print(json.dumps({"status": result["status"], "adapter_dir": result["adapter_dir"],
                      "logits_delta_l1": result["metrics"]["logits_delta_l1"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
