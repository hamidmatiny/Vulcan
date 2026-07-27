# FSDP/DDP CPU training (gloo, world_size=2). ADR-009 / ADR-010.

```bash
# From repo root, with torch installed:
PYTHONPATH=. python training/fsdp-ddp/train.py --strategy ddp
PYTHONPATH=. python training/fsdp-ddp/train.py --strategy fsdp
make test-fsdp-ddp
```

Optional status port: **9012** (`VULCAN_FSDP_DDP_PORT`).
