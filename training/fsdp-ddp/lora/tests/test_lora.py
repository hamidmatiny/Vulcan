"""LoRA fine-tune structural tests (ADR-011 / ADR-009 — no hash pins)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "contracts" / "training-job-contract" / "src"))
sys.path.insert(0, str(ROOT / "training" / "fsdp-ddp" / "lora"))

os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")


@pytest.fixture(scope="module")
def lora_result(tmp_path_factory: pytest.TempPathFactory) -> dict:
    base = ROOT / "models" / "artifacts" / "llm" / "gpt2-small"
    if not (base / "config.json").is_file():
        pytest.skip("reference-tiny-llm artifacts missing; run make models-export")

    from train_lora import default_spec, run

    out = tmp_path_factory.mktemp("lora")
    spec = default_spec(str(out))
    spec["hyperparameters"]["max_steps"] = 3
    return run(spec)


def test_adapter_files_and_rank(lora_result: dict) -> None:
    adapter_dir = Path(lora_result["adapter_dir"])
    assert (adapter_dir / "adapter_config.json").is_file()
    assert (adapter_dir / "adapter_model.safetensors").is_file()
    cfg = json.loads((adapter_dir / "adapter_config.json").read_text(encoding="utf-8"))
    assert int(cfg["r"]) == lora_result["lora"]["r"]
    assert lora_result["verification"] == "structural_not_sha256"


def test_logits_delta_nonzero(lora_result: dict) -> None:
    from train_lora import MIN_LOGITS_DELTA_L1

    assert lora_result["metrics"]["logits_delta_l1"] >= MIN_LOGITS_DELTA_L1
