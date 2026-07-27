# Triton TensorRT-LLM engine variant

**Path:** `serving/triton/tensorrt-llm/`  
**Phase:** 16  
**ADR:** [ADR-007](../../../docs/adr/007-advanced-gpu-serving-techniques-scope.md)

Alongside the phase-4 **ONNX Runtime** `triton-engine` (CPU compose / CI), this directory holds a **GPU-only** Triton layout that uses the **`tensorrt_llm` backend**.

| Artifact | Purpose |
|----------|---------|
| [`model_repository/reference_tiny_llm_trtllm/config.pbtxt`](./model_repository/reference_tiny_llm_trtllm/config.pbtxt) | Structural template for Triton’s TensorRT-LLM backend |
| [`Dockerfile.engine.tensorrtllm`](./Dockerfile.engine.tensorrtllm) | Image recipe (NGC Triton+TRT-LLM tag) — **do not build in CI** without matching GPU/driver |
| [`scripts/validate_config_pbtxt.py`](./scripts/validate_config_pbtxt.py) | Structural lint used in CI |

The contract shim on **:9003** stays the same. On a GPU host you point it at this engine instead of the ONNX CPU engine (`TRITON_URL`).

## What CI does / does not do

| CI | Manual (runbook) |
|----|------------------|
| Lint `config.pbtxt` structure | `trtllm-build` on matching GPU + CUDA |
| Validate related resource notes via shared script | Load engines into Triton; measure performance |
| **Never** builds a TensorRT engine or invents tokens/s | Record real numbers only under `docs/benchmarks/` |

See [`docs/runbooks/tensorrt-llm-build.md`](../../../docs/runbooks/tensorrt-llm-build.md).
