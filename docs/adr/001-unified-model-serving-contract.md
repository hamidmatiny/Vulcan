# ADR 001 — Unified model serving contract (not per-backend APIs)

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 0 (contract), 1+ (serving backends)

## Context

Vulcan will ship multiple inference runtimes — BentoML, Ray Serve, Triton, vLLM, KServe, plus cloud facades (SageMaker, Bedrock). Each runtime has a native API surface (OpenAI-compatible routes, Triton gRPC/HTTP, BentoML Service APIs, KServe V2, etc.). Exposing those natives north-bound would force the gateway, console, benchmarks, and autoscalers to speak N dialects and re-learn capability discovery per backend.

We need a single contract that:

1. Covers LLM-style and vision-style payloads without inventing a lowest-common-denominator blob.
2. Carries enough resource metadata for GPU scheduling (memory, MIG, quantization, cold start).
3. Is testable in CI without GPUs ([ADR-002](./002-gpu-cost-safety-policy.md)).

## Decision

Adopt **one** backend-agnostic HTTP contract in [`contracts/model-contract/`](../../contracts/model-contract/):

| Endpoint | Role |
|----------|------|
| `GET /health` | Liveness / readiness |
| `GET /metrics` | Prometheus exposition |
| `POST /v1/infer` | Inference via `modality` discriminated union (`llm` \| `vision`) |
| `GET /v1/resources` (+ static manifest) | Resource requirements |

Every serving backend **must** implement this contract exactly. Native backend APIs may exist only *behind* an adapter inside `serving/<backend>/`; they are not the platform contract.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Per-backend public APIs | Gateway/console/benchmarks become N×N adapters; capability discovery diverges; e2e tests explode |
| Lowest-common-denominator binary blob | Loses LLM vs vision structure; weak typing; poor DX for clients |
| Adopt one native API as “the” contract (e.g. OpenAI) | Vision/Triton/KServe fit poorly; couples Vulcan to one vendor dialect |
| gRPC-only internal mesh | Excellent for east-west later; worse local DX and browser/console ergonomics for phase-0 |

## Consequences

**Gains**

- Gateway, console, benchmarks, and autoscalers target one OpenAPI + JSON Schema.
- Backends become swappable behind the same north-bound surface.
- Contract tests in CI catch schema drift before GPU spend.

**Trade-offs (accepted)**

- Some backend-native features (continuous batching knobs, Triton model repository ops, OpenAI tool-calling extensions) are **not** exposed 1:1; they stay adapter-internal until promoted into the contract via a new ADR.
- Adapters add a thin latency/complexity layer per backend.
- Discriminated-union evolution requires coordinated schema versioning when new modalities appear.

## Compliance

- New backends: implement `openapi.yaml` paths + ship `resource-requirements.json` with `cpu_dev_mode: true` for CI/local.
- Contract changes: update OpenAPI + JSON Schema + tests together; bump ADR or add a follow-on ADR for breaking changes.
