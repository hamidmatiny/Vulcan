"""Shared names, instance defaults, and cost notes for SageMaker paths."""

from __future__ import annotations

from dataclasses import dataclass


PIPELINE_NAME = "vulcan-reference-tiny-llm"
MODEL_PACKAGE_GROUP = "vulcan-reference-tiny-llm"
ENDPOINT_NAME = "vulcan-reference-tiny-llm-rt"
# Contract vocabulary: this is the managed "backend" id used in metrics/tags.
BACKEND_ID = "sagemaker"

# Manual-run defaults (CPU-ish). GPU training is opt-in in the runbook.
DEFAULT_TRAIN_INSTANCE = "ml.m5.xlarge"
DEFAULT_TRANSFORM_INSTANCE = "ml.m5.large"
DEFAULT_ENDPOINT_INSTANCE = "ml.m5.large"
# Opt-in GPU shapes for real fine-tunes (never CI).
GPU_TRAIN_INSTANCE = "ml.g4dn.xlarge"
GPU_ENDPOINT_INSTANCE = "ml.g5.xlarge"


@dataclass(frozen=True)
class CostEstimate:
    """Rough USD ballpark for a single manual pipeline + endpoint smoke (us-east-1)."""

    train_instance: str
    train_hours: float
    endpoint_instance: str
    endpoint_hours: float
    train_usd: float
    endpoint_usd: float
    notes: str

    @property
    def total_usd(self) -> float:
        return round(self.train_usd + self.endpoint_usd, 2)


def estimate_manual_smoke_cost(
    *,
    use_gpu: bool = False,
    train_hours: float = 0.25,
    endpoint_hours: float = 0.5,
) -> CostEstimate:
    """Order-of-magnitude only — link AWS pricing pages in the runbook."""
    if use_gpu:
        # Ballpark list prices; operators must verify current AWS pricing.
        train_rate = 0.736  # ml.g4dn.xlarge approx
        ep_rate = 1.006  # ml.g5.xlarge approx
        train_i = GPU_TRAIN_INSTANCE
        ep_i = GPU_ENDPOINT_INSTANCE
        notes = "GPU path; delete endpoint immediately after invoke smoke."
    else:
        train_rate = 0.23  # ml.m5.xlarge approx
        ep_rate = 0.115  # ml.m5.large approx
        train_i = DEFAULT_TRAIN_INSTANCE
        ep_i = DEFAULT_ENDPOINT_INSTANCE
        notes = "CPU path matches CI semantics (simulated train); still billed by AWS."
    return CostEstimate(
        train_instance=train_i,
        train_hours=train_hours,
        endpoint_instance=ep_i,
        endpoint_hours=endpoint_hours,
        train_usd=round(train_rate * train_hours, 2),
        endpoint_usd=round(ep_rate * endpoint_hours, 2),
        notes=notes,
    )
