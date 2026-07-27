# Runbook: TensorRT-LLM build and Triton deploy (manual GPU host)

**Manual only.** CI never runs `trtllm-build`, never builds `Dockerfile.engine.tensorrtllm`, and never invents tokens/s ([ADR-002](../adr/002-gpu-cost-safety-policy.md), [ADR-007](../adr/007-advanced-gpu-serving-techniques-scope.md)).

Use this when you have a workstation or cluster node with a supported NVIDIA GPU, matching driver/CUDA for the NGC tag in [`serving/triton/tensorrt-llm/Dockerfile.engine.tensorrtllm`](../../serving/triton/tensorrt-llm/Dockerfile.engine.tensorrtllm).

## Do not add this to CI

| Step | Why it stays human-operated |
|------|-----------------------------|
| `trtllm-build` | Requires GPU + large image pulls; minutes–hours |
| Docker build of `*:tensorrtllm` | Same GPU/driver coupling; fails on CPU runners |
| Load test / quality eval | Hardware-specific; archive under `docs/benchmarks/` only after a real run |

CI’s job is limited to: `make validate-advanced-gpu` (schema + `config.pbtxt` structure).

## Prerequisites

- NVIDIA GPU with a driver compatible with the chosen NGC Triton+TRT-LLM tag (pin documented in the Dockerfile).
- Phase-1 (or larger) HF/safetensors checkpoint available on the build host.
- Docker with the NVIDIA Container Toolkit (`nvidia-smi` works inside `--gpus all`).
- Vulcan contract shim image `vulcan-triton:cpu` (or GPU rebuild) to keep `/v1/infer` north-bound.

Validate templates first (same as CI):

```bash
make validate-advanced-gpu
```

## 1. Build a TensorRT-LLM engine (`trtllm-build`)

Exact CLI flags drift with TensorRT-LLM releases. Follow the [NVIDIA TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM) docs for your version. Sketch:

```bash
# Example shape only — replace paths/flags from upstream docs for your TRT-LLM version.
trtllm-build \
  --checkpoint_dir /path/to/converted-checkpoint \
  --output_dir /path/to/engine_outputs \
  --gemm_plugin float16 \
  --max_batch_size 64 \
  --max_input_len 1024 \
  --max_seq_len 1024
```

Copy engine artifacts into the Vulcan model repository version directory:

```bash
OUT=serving/triton/tensorrt-llm/model_repository/reference_tiny_llm_trtllm/1
mkdir -p "$OUT"
cp -a /path/to/engine_outputs/. "$OUT/"
# Ensure config.pbtxt gpt_model_path still points at
# /models/reference_tiny_llm_trtllm/1 inside the container.
```

## 2. Build and run the Triton TensorRT-LLM engine image

```bash
docker build -f serving/triton/tensorrt-llm/Dockerfile.engine.tensorrtllm \
  -t vulcan-triton-engine:tensorrtllm .

docker run --rm --gpus all -p 8000:8000 -p 8001:8001 \
  vulcan-triton-engine:tensorrtllm
```

Confirm Triton ready:

```bash
curl -fsS http://127.0.0.1:8000/v2/health/ready
curl -fsS http://127.0.0.1:8000/v2/models/reference_tiny_llm_trtllm
```

## 3. Point the Vulcan contract shim at the engine

```bash
# Shim still publishes the phase-0 contract on :9003
docker run --rm -p 9003:9003 \
  -e TRITON_URL=host.docker.internal:8000 \
  -e VULCAN_RUNTIME_MODE=gpu \
  vulcan-triton:cpu
```

(On Linux you may use `--network host` or the engine’s compose service DNS instead of `host.docker.internal`.)

Exercise the contract (manual):

```bash
curl -fsS http://127.0.0.1:9003/health | python3 -m json.tool
# /v1/infer payloads unchanged from phase-4 — model_id=reference-tiny-llm
```

## 4. Optional: record a real GPU benchmark

```bash
BASE_URL=http://127.0.0.1:9003 \
MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
VUS=8 DURATION=60s BACKEND_NAME=triton \
RESULTS_OUT=docs/benchmarks/triton-tensorrtllm-gpu.json \
bash benchmark/scripts/run_k6.sh
```

Do **not** overwrite `benchmark/results/triton-cpu.json` with GPU numbers.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `trtllm-build` CUDA / driver errors | NGC tag vs host driver matrix; `nvidia-smi`; install matching CUDA |
| Triton model fails to load | `gpt_model_path` vs files under `1/`; read Triton logs for missing engine files |
| `KIND_GPU` but no device | Container missing `--gpus all` / device plugin |
| Shim 503 / unhealthy | Engine `/v2/health/ready` false; network from shim → engine |
| Decoupled / streaming errors | Template sets `model_transaction_policy.decoupled`; match client expectations |
| Want this in GitHub Actions | **Stop** — violates ADR-002/007; keep validate-only |

## Tear down

```bash
docker rm -f "$(docker ps -q --filter ancestor=vulcan-triton-engine:tensorrtllm)" 2>/dev/null || true
# Remove local engine blobs if you do not want them on disk
rm -rf serving/triton/tensorrt-llm/model_repository/reference_tiny_llm_trtllm/1/*
# keep .gitkeep
```

Do not add this build/apply flow to GitHub Actions.
