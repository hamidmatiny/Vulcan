# Vulcan Architecture

North-star design for Vulcan: multi-backend model serving and GPU orchestration with a single contract and strict cost-safety for automation. Implementation lands phase-by-phase; this file is the target shape.

## Goals

- **One serving contract** every backend implements exactly ([ADR-001](./docs/adr/001-unified-model-serving-contract.md))
- **Swappable runtimes** — BentoML, Ray Serve, Triton, vLLM, KServe — behind the same north-bound API
- **GPU orchestration** — GPU Operator, MIG, Kueue, Karpenter, checkpointing — validated in CI, applied out-of-band ([ADR-002](./docs/adr/002-gpu-cost-safety-policy.md))
- **Local/prod parity** — same contracts and images from docker compose (CPU-dev) to EKS/GitOps
- **Observability + console** for operators without coupling UI to a single backend dialect

## Component responsibilities

| Component | Responsibility |
|-----------|----------------|
| **contracts/model-contract** | OpenAPI + JSON Schema: `/health`, `/metrics`, `/v1/infer`, resource-requirements |
| **serving/common** | Shared adapters, middleware, CPU-dev reference runners |
| **serving/{bentoml,ray-serve,triton,vllm,kserve}** | Backend-specific packaging that implements the contract |
| **models** | Reference (CPU) and production model packages / manifests |
| **gateway** | Authn/authz, routing, rate limits across backends |
| **benchmark** | Latency/throughput harnesses against the contract |
| **gpu-infra/** | GPU Operator, MIG profiles, Kueue — validate-only in CI |
| **autoscaling/** | Karpenter GPU pools, checkpoint/restore for scale-to-zero |
| **pipelines/** | Kubeflow + SageMaker train → package → deploy paths |
| **bedrock-gateway** | Bedrock facade aligned to the contract where applicable |
| **infra/** | Terraform, Helm, Argo CD (plan/template in CI; apply manual/GitOps) |
| **observability** | Prometheus / Grafana / OTel / SLOs |
| **console** | Operator UI |
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
| Terraform | `validate` / `plan` | `apply` out-of-band |
| Helm | `template` + kubeconform | Argo CD sync |
| Policy | conftest / OPA | Same policies in cluster |
| Benchmarks | Not run | [`docs/benchmarks/`](./docs/benchmarks/) |

## Phased delivery (indicative)

| Phase | Focus |
|-------|--------|
| **0** | Monorepo, model contract, ADR-001/002, CI skeleton, Cursor rules |
| **1** | Reference model pins, conformance suite + client SDK, k6 harness |
| **2+** | First real CPU-dev backend(s), gateway stub |
| **N** | Remaining backends, GPU infra manifests (validate-only), autoscaling |
| **N** | Pipelines, Bedrock facade, observability, console, e2e |
| **16** | Finalize cross-backend benchmark comparison from `benchmark/results/` |

## Non-goals (phase 0)

- No real inference runtime wired in compose yet
- No cloud apply pipelines
- No GPU runners in GitHub Actions
