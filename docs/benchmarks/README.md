# Benchmarks (manual GPU runs)

> **Policy:** Real GPU benchmark runs are **manual** and documented here. CI never provisions or executes against GPU hardware ([ADR-002](../adr/002-gpu-cost-safety-policy.md)).

## How to record a run

1. Provision hardware out-of-band (personal workstation, reserved cluster, etc.).
2. Deploy a contract-compliant backend with an explicit GPU mode override.
3. Run the harness from `benchmark/` (when implemented) against `/v1/infer`.
4. Check in a dated markdown note under this directory:

```text
docs/benchmarks/YYYY-MM-DD-<backend>-<model>.md
```

Include: hardware SKU, driver/CUDA versions, model id, concurrency, latency/throughput, cost estimate, and command lines.

## Phase 0

No benchmark results yet — scaffolding only.
