"""Train step for ``reference-tiny-llm`` (GPT-2 fine-tune path).

CI and default SageMaker CPU jobs use a deterministic CPU simulation (same
digest/loss schedule as ``autoscaling/checkpointing``) so we never download
weights or touch GPUs in automation ([ADR-002](../../../docs/adr/002-gpu-cost-safety-policy.md)).

Set ``VULCAN_SAGEMAKER_REAL_TRAIN=1`` only for manual AWS runs with transformers
installed in the training image (see runbook).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from vulcan_sagemaker.pins import MODEL_ID, load_reference_llm_pin


def simulate_finetune(*, total_steps: int = 20) -> dict[str, Any]:
    """Deterministic stand-in for GPT-2 fine-tune (no torch)."""
    pin = load_reference_llm_pin()
    weight_digest = 0
    loss = 1.0
    for step in range(1, total_steps + 1):
        loss = max(0.01, 1.0 / (1.0 + 0.1 * step))
        weight_digest = (weight_digest * 31 + step) % 1_000_000_007
    return {
        "model_id": pin.model_id,
        "hub_repo_id": pin.repo_id,
        "revision": pin.revision,
        "modality": pin.modality,
        "steps": total_steps,
        "train_loss": loss,
        "weight_digest": weight_digest,
        "mode": "simulate",
    }


def write_model_artifacts(output_dir: Path, metrics: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.tar.json"
    # Lightweight artifact pointer — real runs pack HF weights into model.tar.gz.
    payload = {
        "format": "vulcan-simulated-checkpoint",
        "metrics": metrics,
        "serving": {
            "model_id": MODEL_ID,
            "backend": "sagemaker",
            "contract_modality": "llm",
        },
    }
    model_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "train_metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return model_path


def run_training(
    *,
    output_dir: Path,
    total_steps: int = 20,
    real_train: bool | None = None,
) -> dict[str, Any]:
    if real_train is None:
        real_train = os.environ.get("VULCAN_SAGEMAKER_REAL_TRAIN", "") == "1"
    if real_train:
        raise RuntimeError(
            "VULCAN_SAGEMAKER_REAL_TRAIN=1 requires a transformers-enabled training "
            "image; use the manual runbook GPU path. CI must keep this unset."
        )
    metrics = simulate_finetune(total_steps=total_steps)
    write_model_artifacts(output_dir, metrics)
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vulcan SageMaker train step")
    parser.add_argument("--output-dir", type=Path, default=Path("/opt/ml/model"))
    parser.add_argument("--total-steps", type=int, default=20)
    args = parser.parse_args(argv)
    metrics = run_training(output_dir=args.output_dir, total_steps=args.total_steps)
    print(json.dumps(metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
