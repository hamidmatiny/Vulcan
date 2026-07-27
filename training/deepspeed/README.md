# DeepSpeed CPU ZeRO-1/2 backend (ADR-009 / ADR-010).

```bash
pip install deepspeed torch
PYTHONPATH=. python training/deepspeed/train.py --zero-stage 1
make test-deepspeed
```

GPU ZeRO offload (manual only): [`docs/runbooks/deepspeed-gpu-mode.md`](../../docs/runbooks/deepspeed-gpu-mode.md).

Optional status port: **9013** (`VULCAN_DEEPSPEED_PORT`).
