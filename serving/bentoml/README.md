# serving/bentoml

BentoML adapter that serves **both** phase-1 reference models behind the phase-0 Vulcan model contract.

| Host port | Service |
|-----------|---------|
| **9000** | This backend (`VULCAN_BENTOML_PORT`) |

Vulcan host ports are **9000–9099** (see `.cursor/rules` and root `docker-compose.yml`).

## BentoML’s model (how packaging works)

BentoML wraps a Python **Service** class (`@bentoml.service`) as a deployable unit (“Bento”): dependencies, models, and an HTTP server. APIs are usually declared with `@bentoml.api`, which generates OpenAPI routes under BentoML’s own conventions.

Vulcan needs a **fixed** north-bound surface (`/health`, `/metrics`, `/v1/infer`, `/v1/resources`). This adapter therefore:

1. Declares a BentoML `VulcanService` that **eager-loads** the two reference models in `__init__`.
2. Mounts a FastAPI app with `@bentoml.asgi_app` that implements the contract routes **exactly**.
3. Keeps native BentoML APIs off the platform surface (ADR-001) — clients only speak the Vulcan contract.

```text
Client → GET/POST contract routes (FastAPI mount)
                ↓
         VulcanService (BentoML)
                ↓
    GPT-2 (transformers/safetensors) + ResNet-18 (ONNX Runtime)
```

## Contract mapping

| Contract | Implementation |
|----------|----------------|
| `GET /health` | Ready when both models loaded; `backend=bentoml`, `mode=cpu\|gpu` |
| `GET /metrics` | Prometheus via `prometheus_client` (`vulcan_infer_*`) |
| `POST /v1/infer` | `modality=llm` → GPT-2 generate; `modality=vision` → ResNet-18 ONNX |
| `GET /v1/resources` | [`resource-requirements.json`](./resource-requirements.json) |

`model_id` values:

- `reference-tiny-llm` — GPT-2 small from `models/artifacts/llm/gpt2-small` ([MANIFEST](../../models/MANIFEST.md))
- `reference-tiny-vision` — ResNet-18 ONNX from `models/artifacts/vision/resnet18`

## Resource-requirements (CPU-dev)

From [`resource-requirements.json`](./resource-requirements.json):

| Field | Value | Meaning |
|-------|-------|---------|
| `gpu_memory_mib` | min/max **0** | CPU-dev artifact; no GPU reservation |
| `supports_mig` | `false` | MIG not used in CPU-dev |
| `supports_quantization` | `true` | Quantized weights can be swapped later |
| `cold_start_seconds` | 5–60 | Model load window on CPU |
| `cpu_dev_mode` | **`true`** | Eligible for CI / `make up` (ADR-002) |

## Local run

```bash
make models-export          # once — pin-identical weights
make up                     # starts vulcan-bentoml on :9000
curl -s localhost:9000/health
VULCAN_BACKEND_URL=http://127.0.0.1:9000 make test-serving-common
make benchmark-bentoml      # short CPU k6 → benchmark/results/bentoml-cpu.json
```

Docker-only:

```bash
docker build -f serving/bentoml/Dockerfile -t vulcan-bentoml:cpu .
docker run --rm -p 9000:9000 vulcan-bentoml:cpu
```

## GPU Bento build (manual — not CI)

Per [ADR-002](../../docs/adr/002-gpu-cost-safety-policy.md), CI never builds or runs GPU images. Out-of-band:

```bash
# See bentofile.gpu.yaml — example only
bentoml build -f serving/bentoml/bentofile.gpu.yaml
# then containerize with a CUDA base your cluster supports
```

Set `VULCAN_RUNTIME_MODE=gpu` in that image so `/health` reports `mode=gpu`. Record real GPU numbers under `docs/benchmarks/`, not in CI.
