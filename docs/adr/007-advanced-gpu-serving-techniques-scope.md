# ADR 007 — Advanced GPU serving techniques scope

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 16 (`serving/vllm/gpu-variants/`, `serving/vllm/docs/gpu-mode.md`, `serving/triton/tensorrt-llm/`)

## Context

Phase 5 declared `supports_quantization: true` on the vLLM resource manifest and sketched GPU continuous batching / PagedAttention. Operators still need **concrete** quantization packaging, speculative-decoding launch pairs, and a TensorRT-LLM Triton path. Those techniques **cannot** be executed in Vulcan CI: they need real GPUs, matching CUDA/drivers, and often offline weight conversion (`trtllm-build`, AutoGPTQ/AutoAWQ, FP8 exports).

## Decision

### In scope (real config + docs; validate-only in CI)

1. **vLLM GPU launch documentation** (`serving/vllm/docs/gpu-mode.md`) covering continuous batching (`max_num_seqs`, `max_num_batched_tokens`), PagedAttention KV flags vs the CPU contiguous-KV path, and speculative decoding (`speculative_model` + `num_speculative_tokens`).
2. **Quantization variants** under `serving/vllm/gpu-variants/{gptq,awq,fp8}/` — each with a schema-valid `resource-requirements.json` where `supports_quantization: true`, `cpu_dev_mode: false`, and `gpu_memory_mib` reflects **declared** weight-compression envelopes for `reference-tiny-llm` (not measured VRAM).
3. **Triton TensorRT-LLM engine variant** under `serving/triton/tensorrt-llm/` — `config.pbtxt` template + `Dockerfile.engine.tensorrtllm` + manual runbook. CI **structurally lints** the template only.

### Explicitly out of scope for CI / in-repo claims

| Forbidden | Why |
|-----------|-----|
| Building TensorRT engines in GitHub Actions | Needs `trtllm-build` on matching GPU hardware |
| Running GPTQ/AWQ/FP8 or speculative decoding in CI | Needs CUDA + converted checkpoints |
| Inventing tokens/s, latency, or quality for any variant | Violates ADR-002 honesty; acceptance rates are hardware-specific |

### Why these quantization formats

| Format | Why documented |
|--------|----------------|
| **GPTQ** | Widely supported weight-only path in vLLM; strong ecosystem (AutoGPTQ) for INT4-class checkpoints |
| **AWQ** | Activation-aware alternative with first-class vLLM `--quantization awq` support |
| **FP8** | Newer high-throughput path on recent NVIDIA architectures; distinct from INT4 weight-only |

We do **not** add GGUF/llama.cpp-style formats here — out of vLLM/Triton north-bound scope for this phase.

### Why speculative decoding is documented, not benchmarked

Speedup depends on draft acceptance rate, draft/target size ratio, and sampling settings. Publishing a fake “2.1×” in-repo would be fiction. ADR-007 requires docs to state the **pairing** and workload fit, and to push all numbers to **manual** `docs/benchmarks/` after a real GPU run.

### Restatement — no invented performance numbers

No file under `serving/vllm/gpu-variants/`, `serving/triton/tensorrt-llm/`, or the GPU docs may claim measured throughput, latency percentiles, or quality deltas for these techniques unless accompanied by a dated artifact under `docs/benchmarks/` from a real GPU host. Declared `gpu_memory_mib` values are **scheduler planning envelopes** labeled as such in `notes`.

## Consequences

- Schedulers can distinguish quantized packs via separate manifests while the contract `model_id` stays `reference-tiny-llm`.
- CI grows a path-filtered **validate-only** job (JSON Schema + `config.pbtxt` lint) — never `docker build` of the TensorRT-LLM image in Actions.
- ADR gate: changes under `serving/vllm/gpu-variants/**` or `serving/triton/tensorrt-llm/**` require this ADR.

## Compliance

`check-adr-gate.sh` maps those paths → `007-advanced-gpu-serving-techniques-scope.md`.
