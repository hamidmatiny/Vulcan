# vLLM GPU mode (manual — not CI)

Per [ADR-002](../../../docs/adr/002-gpu-cost-safety-policy.md), Vulcan CI and `make up` never provision GPUs. The compose default is the **CPU OpenAI-compatible small-model path** (transformers + phase-1 GPT-2) so contract/conformance stays green without CUDA.

## What GPU mode unlocks

| Feature | CPU path (compose/CI) | GPU `vllm serve` |
|---------|----------------------|------------------|
| Continuous batching | No | Yes — scheduler packs concurrent requests |
| PagedAttention | No | Yes — paged KV cache, high concurrency |
| Tensor parallelism | No | Yes — `--tensor-parallel-size N` across GPUs |
| Throughput under load | Single-request HF generate | Production serving throughput |

## Launch real vLLM (OpenAI-compatible)

Point the contract shim at this server (`VLLM_URL`, `VULCAN_RUNTIME_MODE=gpu`):

```bash
# Example: HF model or local weights directory
vllm serve openai-community/gpt2 \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype float16 \
  --tensor-parallel-size 1 \
  --max-model-len 1024 \
  --gpu-memory-utilization 0.85
```

Multi-GPU:

```bash
vllm serve <model> \
  --tensor-parallel-size 2 \
  --distributed-executor-backend mp \
  --dtype float16
```

Then run the shim with `VLLM_URL=http://<host>:8000`.

## Benchmark (manual GPU host only)

Short contract-level k6 (same harness as CI, against the shim):

```bash
BASE_URL=http://127.0.0.1:9004 \
MODEL_TYPE=llm MODEL_ID=reference-tiny-llm \
VUS=8 DURATION=60s BACKEND_NAME=vllm \
RESULTS_OUT=docs/benchmarks/vllm-gpu.json \
bash benchmark/scripts/run_k6.sh
```

Native vLLM throughput (engine port, not the Vulcan shim):

```bash
# From a vLLM install / container with GPU
vllm bench serve \
  --backend vllm \
  --base-url http://127.0.0.1:8000 \
  --model openai-community/gpt2 \
  --dataset-name random \
  --num-prompts 200
```

Record numbers under [`docs/benchmarks/`](../../../docs/benchmarks/). Never treat `benchmark/results/vllm-cpu.json` as a GPU claim.
