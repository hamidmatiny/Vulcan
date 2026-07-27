# Vulcan Architecture

North-star design for Vulcan: multi-backend model **serving** and **training**, GPU
orchestration, experiment tracking, and a tool-grounded advisor — all behind shared
contracts, with strict cost-safety for automation. Implementation through phase 22 is
on `main` (`CHANGELOG.md` `[1.2.0]`); this file is the current shape, not a phase-0 sketch.

## Goals

- **One serving contract** every backend implements exactly ([ADR-001](./docs/adr/001-unified-model-serving-contract.md))
- **One training-job contract** for Ray Train / FSDP-DDP / DeepSpeed / LoRA ([ADR-010](./docs/adr/010-unified-training-job-contract.md), [ADR-011](./docs/adr/011-lora-peft-adapter-serving-integration.md))
- **Swappable runtimes** — BentoML, Ray Serve, Triton, vLLM, KServe — behind the same north-bound API
- **Pluggable experiment tracking** — MLflow (self-hosted) + W&B (offline-only) behind one interface ([ADR-013](./docs/adr/013-pluggable-experiment-tracking.md))
- **Tool-grounded advisor** — LangGraph recommendations from Prometheus, benchmarks, and gateway routing only ([ADR-014](./docs/adr/014-langgraph-advisor-non-fabrication-scope.md))
- **GPU orchestration** — GPU Operator, MIG, Kueue, Karpenter, checkpointing — validated in CI, applied out-of-band ([ADR-002](./docs/adr/002-gpu-cost-safety-policy.md), [ADR-009](./docs/adr/009-gpu-cost-safety-extends-to-training.md))
- **Local/prod parity** — same contracts and images from docker compose (CPU-dev) to EKS/GitOps
- **Observability + console** for operators without coupling UI to a single backend dialect

## Component responsibilities

| Component | Responsibility |
|-----------|----------------|
| **contracts/model-contract** | OpenAPI + JSON Schema: `/health`, `/metrics`, `/v1/infer`, resource-requirements |
| **contracts/training-job-contract** | `TrainingJobSpec` / `TrainingJobResult` (+ LoRA fine-tune schemas) |
| **serving/common** | Shared adapters, middleware, CPU-dev reference runners |
| **serving/{bentoml,ray-serve,triton,vllm,kserve}** | Backend-specific packaging that implements the serving contract |
| **training/{ray-train,fsdp-ddp,deepspeed}** | CPU-simulated distributed training (`gloo`, world_size=2 in CI); LoRA under `fsdp-ddp/lora/` |
| **training/common/tracking.py** | Pluggable `ExperimentTracker` (`none` \| `mlflow` \| `wandb`); default `none` |
| **advisor/** | LangGraph tool-grounded routing/cost advisor; non-fabrication CI |
| **models** | Reference (CPU) and production model packages / manifests; DVC for deterministic exports |
| **gateway** | Benchmark-driven routing + health fallback across backends (ADR-006) |
| **benchmark** | Latency/throughput harnesses against the serving contract |
| **gpu-infra/** | GPU Operator, MIG profiles, Kueue — validate-only in CI |
| **autoscaling/** | Karpenter GPU pools, checkpoint/restore for scale-to-zero |
| **pipelines/** | Kubeflow + SageMaker train → package → deploy paths |
| **bedrock-gateway** | Bedrock facade aligned to the contract where applicable |
| **infra/** | Terraform, Helm, Argo CD (plan/template in CI; apply manual/GitOps) |
| **observability** | Prometheus / Grafana / Tempo / OTel / cost-exporter / GPU metrics |
| **console** | Operator UI (stub) |
| **tests/e2e** | Compose-level smoke (CPU-only) |

## Serving data path

```text
client → gateway → POST /v1/infer ─┬→ serving/vllm (adapter)
                                   ├→ serving/triton
                                   ├→ serving/ray-serve
                                   ├→ serving/bentoml
                                   └→ serving/kserve
         GET /health  /metrics  /v1/resources  (same on every backend)
```

`/v1/infer` uses a **discriminated union** on `modality`:

- `llm` — chat messages, sampling knobs, token usage
- `vision` — image(s) + optional prompt, labels and/or text

## Training + tracking path

```text
TrainingJobSpec → training/{ray-train|fsdp-ddp|deepspeed} → TrainingJobResult
                      └─(opt-in)→ ExperimentTracker → MLflow :9014 | W&B offline dir
```

## Advisor data path

```text
question → advisor LangGraph
             ├→ query_prometheus (:9008)
             ├→ read_benchmark_results (benchmark/results/*-cpu.json)
             ├→ query_routing_history (gateway /v1/infer → routing)
             └→ recommend (template ± local reference-tiny-llm)
```

## Resource requirements

Each model+backend pair declares:

- `gpu_memory_mib.{min,max}`
- `supports_mig`
- `supports_quantization`
- `cold_start_seconds.{min,max}`
- `cpu_dev_mode` — **must be true** for CI/compose artifacts

Schedulers (Kueue, Karpenter) consume this manifest; they never appear in CI apply paths.

## GPU cost-safety

| Layer | CI / automation | Human / GitOps |
|-------|-----------------|----------------|
| Serving tests | CPU-dev + reference model | Optional GPU |
| Training tests | CPU `gloo` world_size=2 only | Optional GPU (runbooks) |
| Terraform | `validate` / `plan` | `apply` out-of-band |
| Helm | `template` + kubeconform | Argo CD sync |
| Policy | conftest / OPA | Same policies in cluster |
| Benchmarks | CPU k6 artifacts only | [`docs/benchmarks/`](./docs/benchmarks/) |

## Phased delivery (summary through phase 22)

Detail and commit hashes live in [`CHANGELOG.md`](./CHANGELOG.md). Condensed:

| Phases | Focus |
|--------|--------|
| **0–5** | Contract, reference models, BentoML / Ray Serve / Triton / vLLM adapters |
| **6–9** | KServe; GPU Operator / MIG / Kueue / Karpenter + checkpointing (validate-only) |
| **10–12** | SageMaker (moto), Bedrock gateway, Kubeflow → KServe |
| **13–15** | Routing gateway, observability, security/docs → **v1.0.0** |
| **16–17** | Advanced GPU packaging (ADR-007); cost-per-token + synthetic DCGM (ADR-008) |
| **18–20** | Training backends + contract; LoRA/PEFT; DVC for deterministic exports |
| **21–22** | Pluggable MLflow/W&B tracking; LangGraph advisor → **`[1.2.0]` on main** |

## Standing non-goals (still true)

These replace the old “Non-goals (phase 0)” list — phase 0 placeholders no longer apply.

- **No real GPU hardware in CI** — no cloud GPU nodes, no invented tokens/s ([ADR-002](./docs/adr/002-gpu-cost-safety-policy.md), [ADR-007](./docs/adr/007-advanced-gpu-serving-techniques-scope.md), [ADR-009](./docs/adr/009-gpu-cost-safety-extends-to-training.md))
- **No live cloud LLM calls in CI** — advisor uses local tools + pinned `reference-tiny-llm`; hosted LLM is manual opt-in only ([ADR-014](./docs/adr/014-langgraph-advisor-non-fabrication-scope.md))
- **No live wandb.ai / cloud MLflow SaaS in CI** — W&B offline-only; MLflow self-hosted on `:9014` ([ADR-013](./docs/adr/013-pluggable-experiment-tracking.md))
- **No automated `terraform apply` / Helm install of GPU pools** — validate/plan/template only; apply is human/GitOps
