# DeepSpeed GPU mode (manual only — ADR-009)

CI and default local paths run DeepSpeed with **CPU + `gloo` + world_size=2** and ZeRO stage 1–2
without claiming GPU throughput.

## Real GPU ZeRO offload

1. Provision a GPU node **out-of-band** (never via CI automation — ADR-002 / ADR-009).
2. Install a CUDA build of PyTorch + DeepSpeed matching your driver.
3. Set `cpu_dev_mode: false`, `distributed.dist_backend: nccl`, and enable
   `zero_optimization.cpu_offload` / NVMe offload in `ds_config.json` as appropriate.
4. Launch with the DeepSpeed launcher against your GPU count.
5. Record measured samples/sec and steps/sec under [`docs/benchmarks/`](../benchmarks/) —
   **do not invent numbers in-repo**.

This runbook intentionally does not embed fabricated tokens/s or $/step GPU figures.
