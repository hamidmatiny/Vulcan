# serving/triton

NVIDIA **Triton Inference Server** adapter: ONNX models in a Triton **model repository**, plus a thin HTTP **contract shim** on host port **9003** that implements the phase-0 Vulcan surface exactly.

| Host port | Service |
|-----------|---------|
| **9003** | Contract shim (`VULCAN_TRITON_PORT`) → Triton engine (internal `:8000`) |

Vulcan host ports are **9000–9099** (see `.cursor/rules` and root `docker-compose.yml`).

## Architecture

```text
Client → contract shim (:9003)  — /health /metrics /v1/infer /v1/resources
              ↓  Triton HTTP/JSON (v2)
     triton-engine (internal :8000/:8001/:8002)
              ↓
     model_repository/
       reference_tiny_llm/1/model.onnx      ← GPT-2 ONNX (from phase-1 safetensors)
       reference_tiny_vision/1/model.onnx   ← ResNet-18 ONNX (byte-identical pin)
```

Contract `model_id` values stay hyphenated (`reference-tiny-llm` / `reference-tiny-vision`). Triton model **names** use underscores (`reference_tiny_llm` / `reference_tiny_vision`) because Triton identifiers disallow hyphens.

## Model repository concept

Triton loads models from a directory tree:

```text
model_repository/
  <model_name>/
    config.pbtxt          # platform, inputs/outputs, batching, instance_group
    1/
      model.onnx          # version directory (integer)
```

- **`config.pbtxt`** declares the ONNX Runtime backend (`platform: "onnxruntime_onnx"`), tensor names/shapes, and whether the model runs on CPU or GPU.
- **Version directories** (`1/`, `2/`, …) hold the artifact; Triton can load the latest or a pinned version.
- **`dims` omit the batch axis** when `max_batch_size > 0`; Triton prepends batch.

Prepare ONNX into this tree (after `make models-export`):

```bash
make triton-prepare
```

Vision copies the pinned ResNet-18 ONNX. LLM exports GPT-2 ONNX from the pinned safetensors (same weight pin; ONNX bytes are a derived artifact).

## Dynamic batching

Both configs enable Triton’s scheduler:

```protobuf
dynamic_batching {
  preferred_batch_size: [ 1, 2, 4, 8 ]   # vision; llm uses [1, 2, 4]
  max_queue_delay_microseconds: 200
}
```

Triton holds requests briefly to form larger batches up to `max_batch_size`, improving GPU/CPU throughput under concurrent load. The contract shim still sends one logical request at a time; concurrency comes from multiple HTTP clients (e.g. k6).

## Contract mapping

| Contract | Implementation |
|----------|----------------|
| `GET /health` | Ready when Triton reports both models ready; `backend=triton` |
| `GET /metrics` | Prometheus on the shim (`vulcan_infer_*`) |
| `POST /v1/infer` | `llm` → tokenize + greedy loop over Triton GPT-2; `vision` → preprocess + Triton ResNet |
| `GET /v1/resources` | [`resource-requirements.json`](./resource-requirements.json) |

## Resource-requirements (CPU-dev)

| Field | Value |
|-------|-------|
| `gpu_memory_mib` | min/max **0** |
| `supports_mig` | `true` (Triton/MIG-capable; unused in CPU-dev) |
| `supports_quantization` | `true` |
| `cold_start_seconds` | 15–120 |
| `cpu_dev_mode` | **`true`** |

## Local run

```bash
make models-export
make triton-prepare
make up                      # --wait until healthy (bentoml/ray-serve/triton)
VULCAN_BACKEND_URL=http://127.0.0.1:9003 make test-serving-common
make benchmark-triton        # → benchmark/results/triton-cpu.json
```

`make up` uses `docker compose --wait`. Conformance and `benchmark-*` also call
`make wait-for-health` (same poll loop as CI) so you do not need a manual sleep
between `up` and tests. The shim is `ok` only when Triton `/v2/health/ready`
and both `/v2/models/{reference_tiny_llm,reference_tiny_vision}/ready` succeed.

Compose services:

| Service | Role |
|---------|------|
| `triton-engine` | Official `tritonserver` image, `KIND_CPU`, model repo baked in (no host port) |
| `triton` | FastAPI shim on **:9003** |

On Apple Silicon, `triton-engine` uses `platform: linux/amd64` (QEMU). Prefer an amd64 Linux host for usable latency.

## GPU / TensorRT (manual — not CI)

See [`docs/gpu-tensorrt.md`](./docs/gpu-tensorrt.md): `KIND_GPU`, TensorRT execution accelerator, `--gpus all`. Do not enable in CI ([ADR-002](../../docs/adr/002-gpu-cost-safety-policy.md)).

## perf_analyzer (deeper GPU benchmark later)

NVIDIA ships **`perf_analyzer`** with the Triton SDK / NGC containers. Use it against Triton’s native HTTP/gRPC (not the Vulcan shim) when you have a GPU host:

```bash
# Example — vision model, shape matches config.pbtxt (batch dim omitted in -b)
docker run --rm --gpus all --network host \
  nvcr.io/nvidia/tritonserver:24.05-py3-sdk \
  perf_analyzer -m reference_tiny_vision \
    -u localhost:8000 \
    --concurrency-range 1:8:2 \
    -b 1 \
    --input-data zero \
    --measurement-interval 10000 \
    --shape pixel_values:3,224,224
```

LLM (variable sequence) needs a real input JSON or shared-memory setup — start from the [Triton perf_analyzer docs](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/client/README.html#performance-analyzer). Record GPU numbers under `docs/benchmarks/`; the CI artifact `triton-cpu.json` is a short CPU regression only.

This command is **documented only** — Vulcan CI does not run `perf_analyzer` and does not require GPU hardware.
