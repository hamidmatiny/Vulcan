# benchmark

Load-test harness for contract-compliant Vulcan backends.

## Why k6 (not Locust)

k6 is chosen over Locust because:

1. **Same tooling as Argus** load nightlies — one mental model across sibling repos.
2. **First-class HTTP latency percentiles** (`p50`/`p95`/`p99`) and `handleSummary` JSON without fighting the Python GIL next to a serving process.
3. **Lightweight CI image** (`grafana/k6`) — no heavy Python ML stack required for the driver.

Locust remains fine for exploratory Python scripting; **committed harnesses use k6**.

> GPU policy ([ADR-002](../docs/adr/002-gpu-cost-safety-policy.md)): this harness runs against CPU-dev URLs in CI. Real GPU runs are manual and recorded under [`docs/benchmarks/`](../docs/benchmarks/).

## Quick start

```bash
# Terminal A — trivial reference server (phase-1 proof)
make reference-server

# Terminal B — short smoke load test
make benchmark-smoke

# Compare any results JSON files
make benchmark-compare
```

## Parameters (env)

| Variable | Default | Meaning |
|----------|---------|---------|
| `BASE_URL` | `http://127.0.0.1:8080` | Target backend |
| `MODEL_TYPE` | `llm` | `llm` or `vision` |
| `MODEL_ID` | `reference-tiny-llm` | Contract `model_id` |
| `VUS` | `5` | Concurrent virtual users |
| `DURATION` | `15s` | Test duration |
| `BACKEND_NAME` | `reference` | Label written into results JSON |
| `RESULTS_OUT` | `benchmark/results/<backend>-<modality>.json` | Output path |

## Results

Each run writes a JSON document conforming to [`results/schema.json`](./results/schema.json).  
[`scripts/compare_results.py`](./scripts/compare_results.py) renders a markdown comparison table from any set of those files — reused every backend phase and finalized in phase 16.
