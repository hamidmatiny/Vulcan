# training/ — contract-first training backends

CPU-simulated distributed training behind [`contracts/training-job-contract/`](../contracts/training-job-contract/)
([ADR-009](../docs/adr/009-gpu-cost-safety-extends-to-training.md) /
[ADR-010](../docs/adr/010-unified-training-job-contract.md) /
[ADR-011](../docs/adr/011-lora-peft-adapter-serving-integration.md) /
[ADR-013](../docs/adr/013-pluggable-experiment-tracking.md)).

## Layout

| Path | Role |
|------|------|
| `ray-train/` | Ray Train CPU job (`gloo`, world_size=2) |
| `fsdp-ddp/` | PyTorch FSDP/DDP + SIGTERM resume |
| `fsdp-ddp/lora/` | PEFT LoRA fine-tune on pinned `reference-tiny-llm` |
| `deepspeed/` | DeepSpeed ZeRO-1/2 CPU path ([GPU runbook](../docs/runbooks/deepspeed-gpu-mode.md)) |
| `common/tracking.py` | Pluggable experiment tracker (`none` \| `mlflow` \| `wandb`) |
| `common/runtime.py` | Shared train-loop helpers |

## Local ports (compose profile `training`)

- **9011** — ray-train status
- **9012** — fsdp-ddp status
- **9013** — deepspeed status
- **9014** — MLflow tracking UI

## Tracking (opt-in)

```bash
export VULCAN_TRACKER_BACKEND=none   # default — no deps
# or mlflow  → MLFLOW_TRACKING_URI=http://127.0.0.1:9014
# or wandb   → WANDB_MODE=offline only (no WANDB_API_KEY; no wandb.ai in CI)
```

## Make targets

`make test-ray-train` · `make test-fsdp-ddp` · `make test-deepspeed` · `make test-lora-peft` · `make test-tracking`
