# serving/vllm

**LLM-only** adapter: contract shim on host port **9004** over an OpenAI-compatible engine (vLLM’s API surface).

| Host port | Service |
|-----------|---------|
| **9004** | Contract shim (`VULCAN_VLLM_PORT`) → engine (internal `:8000`) |

Vulcan host ports are **9000–9099** (see `.cursor/rules` and root `docker-compose.yml`).

## LLM-only (explicit)

This adapter implements **only the `llm` branch** of the contract’s `modality` discriminated union (`reference-tiny-llm`).

| Modality | Behavior |
|----------|----------|
| `llm` | Mapped to OpenAI `/v1/chat/completions` on the engine, then back to `/v1/infer` |
| `vision` | **400** contract error: `error=unsupported_modality` with a clear message — not a silent failure |

Use bentoml / ray-serve / triton for `reference-tiny-vision`. Do not treat a vision 400 here as an infrastructure outage.

Conformance against this backend should set `VULCAN_CONFORMANCE_MODALITIES=llm` so the shared vision success test is skipped (suite file unchanged). CI also asserts the vision 400 shape.

## Architecture

```text
Client → contract shim (:9004)  — /health /metrics /v1/infer /v1/resources
              ↓  OpenAI chat completions
     vllm-engine (internal :8000)
              ↓
     CPU path: transformers GPT-2 (phase-1 pin) — CI / compose default
     GPU path: real `vllm serve` — continuous batching, PagedAttention, TP
```

## CPU path vs GPU path

| | **CPU (compose / CI)** | **GPU (manual)** |
|--|------------------------|------------------|
| Engine | [`engine/cpu_openai_server.py`](./engine/cpu_openai_server.py) — OpenAI-compatible small-model path | `vllm serve` ([docs/gpu-mode.md](./docs/gpu-mode.md)) |
| Benefit | Contract correctness without CUDA | Continuous batching, PagedAttention, tensor parallelism |
| Benchmark artifact | `benchmark/results/vllm-cpu.json` | `docs/benchmarks/` only |

CPU mode does **not** claim vLLM’s GPU scheduling benefits. See [docs/gpu-mode.md](./docs/gpu-mode.md) (phase-16: continuous batching, PagedAttention, speculative decoding). Quantized GPU packs: [`gpu-variants/`](./gpu-variants/) ([ADR-007](../../docs/adr/007-advanced-gpu-serving-techniques-scope.md)).

## Contract mapping

| Contract | Implementation |
|----------|----------------|
| `GET /health` | Ready when engine `/v1/models` succeeds; `backend=vllm`; detail notes `vision=unsupported` |
| `GET /metrics` | Prometheus (`vulcan_infer_*`) |
| `POST /v1/infer` | `llm` → chat completions; `vision` → `unsupported_modality` |
| `GET /v1/resources` | [`resource-requirements.json`](./resource-requirements.json) |

## Local run

```bash
make models-export
make up                      # includes vllm :9004 (--wait)
VULCAN_BACKEND_URL=http://127.0.0.1:9004 \
  VULCAN_CONFORMANCE_MODALITIES=llm \
  make test-serving-common
make benchmark-vllm          # wait-for-health + k6 → vllm-cpu.json
```

## Resource-requirements (CPU-dev)

| Field | Value |
|-------|-------|
| `gpu_memory_mib` | min/max **0** |
| `supports_mig` | `true` (GPU path capable; unused in CPU-dev) |
| `cpu_dev_mode` | **`true`** |

Quantized GPU variants (not used in compose) live under [`gpu-variants/`](./gpu-variants/) with `cpu_dev_mode: false`.
