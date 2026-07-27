# vLLM GPU mode (manual — not CI)

Per [ADR-002](../../../docs/adr/002-gpu-cost-safety-policy.md) and [ADR-007](../../../docs/adr/007-advanced-gpu-serving-techniques-scope.md), Vulcan CI and `make up` never provision GPUs and **never invent** throughput, latency, or quality numbers for these features. The compose default remains the **CPU OpenAI-compatible small-model path** (transformers + phase-1 GPT-2).

This document is **launch configuration and trade-off guidance** for a real GPU host. Measure on your hardware; archive results under [`docs/benchmarks/`](../../../docs/benchmarks/) only after a real run.

## What GPU mode unlocks

| Feature | CPU path (compose/CI) | GPU `vllm serve` |
|---------|----------------------|------------------|
| Continuous batching | No — single-request HF generate | Yes — scheduler packs concurrent requests |
| PagedAttention | No — naive contiguous KV for the tiny CPU path | Yes — block-based KV cache |
| Speculative decoding | No | Yes — draft + target pairing (see below) |
| Quantization (GPTQ/AWQ/FP8) | No | Yes — see [`../gpu-variants/`](../gpu-variants/) |
| Tensor parallelism | No | Yes — `--tensor-parallel-size N` |

## Continuous batching

vLLM’s GPU scheduler continuously admits new requests into an in-flight batch instead of waiting for a full static batch to drain.

| Flag | Role | Trade-off |
|------|------|-----------|
| `--max-num-seqs` | Cap on concurrent sequences in the scheduler | Higher → more concurrency / KV pressure; lower → simpler latency for few users |
| `--max-num-batched-tokens` | Cap on tokens processed per scheduling step (prefill+decode across the batch) | Higher → better GPU saturation on long/prefill-heavy traffic; lower → tighter latency tails and less peak activation memory |

Example (still no claimed throughput):

```bash
vllm serve openai-community/gpt2 \
  --host 0.0.0.0 --port 8000 \
  --dtype float16 \
  --max-model-len 1024 \
  --max-num-seqs 64 \
  --max-num-batched-tokens 4096 \
  --gpu-memory-utilization 0.85
```

Tune `max-num-seqs` and `max-num-batched-tokens` together: raising only one often shifts the bottleneck (KV vs compute) without a free lunch.

## KV cache / PagedAttention

| Flag | Role |
|------|------|
| `--block-size` | Tokens per KV **block** (PagedAttention page size). Common defaults are 16 or 32 depending on vLLM version. |
| `--gpu-memory-utilization` | Fraction of GPU memory vLLM may reserve (weights + KV + activations). Raise carefully; OOM kills the engine. |
| `--swap-space` | CPU swap for KV overflow (GiB). Softens spikes; adds latency when swapping. |

### PagedAttention vs the CPU-sim path

| | **CPU compose path** (`engine/cpu_openai_server.py`) | **GPU PagedAttention** |
|--|------------------------------------------------------|-------------------------|
| KV layout | Contiguous per-sequence tensors sized for `max_model_len` (or equivalent HF cache) | Fixed-size **blocks** allocated on demand and remapped as sequences grow |
| Memory | Wastes headroom for short sequences; simple | Packs fragmented lengths; enables much higher concurrent sequences for the same VRAM |
| Continuations / preemption | Not a production KV manager | Block tables allow prepend/append without full-tensor realloc |

The CPU path exists for **contract correctness**, not as a simulator of PagedAttention efficiency.

## Speculative decoding (draft + target)

Speculative decoding proposes several tokens with a cheap **draft** model and verifies them with the **target** (larger / higher-quality) model in one parallel step.

| Flag | Role |
|------|------|
| `--speculative-model` | Hugging Face id or path of the **draft** model |
| `--num-speculative-tokens` | How many draft tokens to propose per verification step |

```bash
# Target = main model; draft = smaller sibling (example ids — replace with your pair)
vllm serve <target-model> \
  --host 0.0.0.0 --port 8000 \
  --dtype float16 \
  --speculative-model <draft-model> \
  --num-speculative-tokens 5
```

Newer vLLM releases may fold these into a `--speculative-config` JSON blob — prefer the flags your installed version documents; the **pairing semantics** (draft proposes, target verifies) stay the same.

### What benefits / what doesn’t

| Workload | Why speculative helps or not |
|----------|------------------------------|
| High-throughput chat with predictable short-ish completions | Often good — draft hits accepted frequently |
| Highly creative / high-temperature sampling | Draft/target disagreement rises → wasted draft work |
| Prefill-dominated (huge prompts, tiny completions) | Less benefit — speculation mainly accelerates **decode** |
| Draft nearly as large as target | Little speedup; you pay for two models in VRAM |

**Why this is documented, not CI-benchmarked:** draft/target acceptance rates and speedups are hardware- and checkpoint-specific. ADR-007 forbids inventing those numbers in-repo; measure on a GPU host and file results under `docs/benchmarks/` if you need them.

## Quantization variants

Declared resource manifests + launch flags: [`../gpu-variants/`](../gpu-variants/) (GPTQ, AWQ, FP8). `supports_quantization: true` on the phase-5 CPU-dev manifest is the capability flag; the variants make that concrete for schedulers.

## Tensor parallelism

```bash
vllm serve <model> \
  --tensor-parallel-size 2 \
  --distributed-executor-backend mp \
  --dtype float16
```

## Point the Vulcan shim at a GPU engine

```bash
export VULCAN_RUNTIME_MODE=gpu
export VLLM_URL=http://<gpu-host>:8000
# shim still on :9004 — same contract
```

## Benchmark (manual GPU host only)

```bash
BASE_URL=http://127.0.0.1:9004 \
MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
VUS=8 DURATION=60s BACKEND_NAME=vllm \
RESULTS_OUT=docs/benchmarks/vllm-gpu.json \
bash benchmark/scripts/run_k6.sh
```

Never treat `benchmark/results/vllm-cpu.json` as a GPU, quantized, or speculative-decoding claim.
