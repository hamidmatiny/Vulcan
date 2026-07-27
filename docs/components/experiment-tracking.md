# Experiment tracking

Pluggable interface at [`training/common/tracking.py`](../../training/common/tracking.py)
([ADR-013](../adr/013-pluggable-experiment-tracking.md)).

| Backend | Env | CI policy |
|---------|-----|-----------|
| `none` (default) | `VULCAN_TRACKER_BACKEND=none` | Existing jobs unchanged |
| `mlflow` | `MLFLOW_TRACKING_URI=http://127.0.0.1:9014` | Self-hosted compose service; assert via tracking API |
| `wandb` | `WANDB_MODE=offline` | Offline run dirs only — never wandb.ai; no `WANDB_API_KEY` |

Wire-through: FSDP/DDP and LoRA report existing loss/throughput through the interface
(no recomputation). See also [`training/`](training.md) and the
[MLflow Dockerfile](../../training/common/Dockerfile.mlflow).
