# model-contract

Backend-agnostic OpenAPI + JSON Schema serving contract. **Every** Vulcan serving backend (`serving/*`) must implement this contract exactly.

## Surface

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness / readiness (`status`: `ok` \| `starting` \| `error`) |
| `GET /metrics` | Prometheus text exposition |
| `POST /v1/infer` | Inference — `modality` discriminated union (`llm` \| `vision`) |
| `GET /v1/resources` | Runtime view of the resource-requirements manifest |

Static packaging also ships a `resource-requirements.json` conforming to
[`schemas/resource-requirements.schema.json`](./schemas/resource-requirements.schema.json)
(`gpu_memory_mib` min/max, `supports_mig`, `supports_quantization`, `cold_start_seconds`, `cpu_dev_mode`).

## Files

| Path | Role |
|------|------|
| [`openapi.yaml`](./openapi.yaml) | Canonical OpenAPI 3.1 spec |
| [`schemas/`](./schemas/) | Standalone JSON Schema (draft 2020-12) |
| [`examples/`](./examples/) | Valid example manifests |
| [`tests/`](./tests/) | Schema / example validation (CI-gated, ≥65% coverage) |

## Design notes

- **One contract, many backends** — see [ADR-001](../../docs/adr/001-unified-model-serving-contract.md).
- **CPU-dev mandatory** — `cpu_dev_mode: true` packages are what CI and `make up` run; see [ADR-002](../../docs/adr/002-gpu-cost-safety-policy.md).
- Native backend APIs (vLLM OpenAI routes, Triton gRPC, etc.) may exist *behind* an adapter, but the **north-bound** Vulcan surface is this contract.

## Validate locally

```bash
make test-contracts
# or
cd contracts/model-contract && python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q --cov=vulcan_model_contract --cov-fail-under=65
```
