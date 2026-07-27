# vLLM GPU quantization variants

**Path:** `serving/vllm/gpu-variants/`  
**Phase:** 16  
**ADR:** [ADR-007](../../../docs/adr/007-advanced-gpu-serving-techniques-scope.md)

These manifests make good on `supports_quantization: true` in the phase-5 [`../resource-requirements.json`](../resource-requirements.json). Each file is a **scheduler-facing declaration** for a quantized packaging of `reference-tiny-llm` under backend `vllm`.

## Honesty (ADR-002 / ADR-007)

| Allowed here | Forbidden here |
|--------------|----------------|
| Declared `gpu_memory_mib` from **format compression ratios** vs FP16 weights for this small reference LLM, plus headroom notes | Throughput, tokens/s, latency percentiles, or quality scores |
| Exact vLLM launch flags for each format | Claiming CI measured these footprints |

`cpu_dev_mode` is **`false`**: these artifacts are **not** for compose/CI runtime. CI only JSON-Schema-validates them.

### Baseline (not a separate manifest)

Phase-1 GPT-2–class (~124M) FP16 weights are on the order of ~250 MiB. Unquantized GPU serving also needs KV/activation headroom. Variants below **reduce the weight term**; KV still scales with concurrency (`max_num_seqs`, context length). Declared min/max are planning envelopes for Kueue/MIG — recalibrate after a real `nvidia-smi` capture on your host.

## Variants

| Directory | Format | Declared `gpu_memory_mib` | Compression claim (weights vs FP16) |
|-----------|--------|---------------------------|-------------------------------------|
| [`gptq/`](./gptq/) | GPTQ (typically W4) | min **512** / max **1024** | ~4× smaller weights |
| [`awq/`](./awq/) | AWQ (typically W4) | min **512** / max **1024** | ~4× smaller weights |
| [`fp8/`](./fp8/) | FP8 | min **768** / max **1536** | ~2× smaller weights |

## Shared launch notes

1. Produce or obtain a checkpoint already quantized for the format (AutoGPTQ / AutoAWQ / FP8 export). Do not assume the safetensors pin in `models/artifacts/` is GPTQ/AWQ/FP8.
2. Point Vulcan’s shim at the engine: `VLLM_URL=…`, `VULCAN_RUNTIME_MODE=gpu`.
3. Prefer the same contract `model_id=reference-tiny-llm` so north-bound clients stay unchanged; track the weight format in deployment labels / notes, not by forking the contract id unless you intentionally version models.
