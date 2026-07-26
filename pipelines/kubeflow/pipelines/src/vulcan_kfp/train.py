"""Local/CI train step — same digest schedule as autoscaling/checkpointing.

Cluster training uses the Training Operator PyTorchJob
(``pipelines/kubeflow/training-operator/``), which runs
``vulcan-checkpoint-finetune`` on Karpenter spot + Kueue ``lq-training``.
This module is the CPU-safe twin used by KFP components and unit tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vulcan_kfp.pins import MODEL_ID, load_reference_llm_pin


def simulate_finetune(*, total_steps: int = 20) -> dict[str, Any]:
    """Mirror autoscaling/checkpointing FineTuneJob digest/loss (no torch)."""
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
        "loss": loss,
        "weight_digest": weight_digest,
        "mode": "simulate",
        "checkpointing": "autoscaling/checkpointing (phase-9 contract)",
    }


def write_model_artifacts(output_dir: Path, metrics: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "train_metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifact = {
        "format": "vulcan-simulated-checkpoint",
        "model_id": MODEL_ID,
        "metrics": metrics,
        "serving_handoff": "kserve-vllm",
    }
    path = output_dir / "model-meta.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_training(*, output_dir: Path, total_steps: int = 20) -> dict[str, Any]:
    metrics = simulate_finetune(total_steps=total_steps)
    write_model_artifacts(output_dir, metrics)
    return metrics
