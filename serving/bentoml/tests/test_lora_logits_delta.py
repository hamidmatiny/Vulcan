"""BentoML LoRA serving proof: base vs base+adapter logits differ (ADR-011)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BENTOML_DIR = ROOT / "serving" / "bentoml"
sys.path.insert(0, str(BENTOML_DIR))
sys.path.insert(0, str(ROOT / "contracts" / "model-contract" / "src"))

FIXED_PROMPT = "user: vulcan lora probe\nassistant:"
MIN_DELTA = 1e-4


@pytest.fixture(scope="module")
def adapter_dir() -> Path:
    env = os.environ.get("VULCAN_LORA_ADAPTER_DIR")
    if env:
        path = Path(env)
    else:
        path = ROOT / "training" / "results" / "lora-demo" / "adapter"
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    if not (path / "adapter_config.json").is_file():
        pytest.skip("LoRA adapter not present; run make test-lora-peft first")
    return path


def test_lora_resource_requirements_valid() -> None:
    from vulcan_model_contract.validate import validate_resource_requirements

    data = json.loads(
        (BENTOML_DIR / "resource-requirements-lora-demo.json").read_text(encoding="utf-8")
    )
    validate_resource_requirements(data)
    assert data["model_id"] == "reference-tiny-llm-lora-demo"


def test_base_vs_lora_logits_differ(adapter_dir: Path) -> None:
    os.environ["VULCAN_LORA_ADAPTER_DIR"] = str(adapter_dir)
    from models_runtime import load_llm, load_llm_with_lora

    base = load_llm(device="cpu")
    lora = load_llm_with_lora(adapter_dir=adapter_dir, device="cpu")
    base_logits = base.logits_for_prompt(FIXED_PROMPT)
    lora_logits = lora.logits_for_prompt(FIXED_PROMPT)
    delta = float((lora_logits - base_logits).abs().mean().item())
    assert delta >= MIN_DELTA, f"expected logits delta ≥ {MIN_DELTA}, got {delta}"
