# training/ — contract-first training backends (ADR-009 / ADR-010 / ADR-011).
#
# CPU-simulated distributed training only in CI (`gloo`, world_size=2).
# LoRA/PEFT fine-tune: training/fsdp-ddp/lora/ (make test-lora-peft).
# Optional local status HTTP (compose profile `training`):
#   9011 — ray-train
#   9012 — fsdp-ddp
#   9013 — deepspeed
