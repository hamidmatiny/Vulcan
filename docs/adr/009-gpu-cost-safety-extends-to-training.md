# ADR 009 — GPU cost-safety extends to training

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 18 (`training/**`, training CI jobs)

## Context

[ADR-002](./002-gpu-cost-safety-policy.md) forbids real GPU spend in CI for **serving**. Phase 18 adds a second axis — **training** backends (Ray Train, native FSDP/DDP, DeepSpeed). Distributed training is even easier to misconfigure into multi-node / multi-GPU cloud spend than inference adapters. The same cost-safety bar must apply without exception.

## Decision

ADR-002’s hard rules **extend to training** unchanged in spirit:

1. **CI never provisions or runs real GPU or multi-node training hardware.**
2. **All three training backends MUST run CPU-simulated distributed training only in CI and default local paths**, using PyTorch’s `gloo` backend with `world_size=2` (two local processes on the same CPU runner / laptop).
3. **No invented GPU/multi-node tokens/s or samples/s.** Real GPU or multi-node throughput, if ever produced, belongs only in manually generated [`docs/benchmarks/`](../benchmarks/) artifacts — never fabricated in-repo or asserted by CI green checks.
4. **DeepSpeed ZeRO GPU offload numbers** require a manual GPU run; see [`docs/runbooks/deepspeed-gpu-mode.md`](../runbooks/deepspeed-gpu-mode.md) (same pattern as vLLM/Triton GPU runbooks).
5. Training job specs carry `cpu_dev_mode: true` for CI/local defaults; `cpu_dev_mode: false` is excluded from CI matrices.

### Checkpoint verification (not byte-hash pins)

Training checkpoints have run-to-run floating-point variance. Unlike `models/MANIFEST.md` weight pins, **do not SHA256-pin raw checkpoints**. CI verifies structurally: schema-valid `metrics.json` / `TrainingJobResult`, loss below a fixed threshold, checkpoint loads and produces a forward pass without error.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Nightly 2-GPU training CI | Recurring spend; quota/flake; easy to expand |
| Mock-only (no real `gloo` world_size=2) | Misses distributed launcher / resume bugs cheaply caught on CPU |
| Hash-pin checkpoints like reference models | Byte variance makes pins flake; wrong tool for FP training |

## Consequences

**Gains**

- Predictable CI cost for the training axis.
- Real distributed semantics (`gloo`, world_size=2, SIGTERM resume) without NVIDIA hardware.

**Trade-offs (accepted)**

- GPU ZeRO / NCCL / multi-node regressions are manual-only.
- CPU `gloo` throughput is **not** a capacity planning signal for GPU clusters.

## Compliance

`check-adr-gate.sh` maps `training/**` → this ADR **and** [ADR-010](./010-unified-training-job-contract.md).
