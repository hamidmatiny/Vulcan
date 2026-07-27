# training/ — contract-first training backends (ADR-009 / ADR-010 / ADR-011 / ADR-013).
#
# CPU-simulated distributed training only in CI (`gloo`, world_size=2).
# LoRA/PEFT fine-tune: training/fsdp-ddp/lora/ (make test-lora-peft).
# Experiment tracking (opt-in): training/common/tracking.py
#   VULCAN_TRACKER_BACKEND=none|mlflow|wandb  (default none)
#   MLflow: MLFLOW_TRACKING_URI=http://127.0.0.1:9014
#   W&B: WANDB_MODE=offline only (no WANDB_API_KEY; no wandb.ai in CI)
# Optional local status HTTP + MLflow (compose profile `training`):
#   9011 — ray-train
#   9012 — fsdp-ddp
#   9013 — deepspeed
#   9014 — MLflow tracking UI
