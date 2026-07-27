# ADR 010 — Unified training job contract (not per-backend APIs)

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 18 (`contracts/training-job-contract/`, `training/*`)

## Context

Vulcan will ship multiple **training** runtimes — Ray Train, native PyTorch FSDP/DDP, and DeepSpeed — alongside the existing serving stack. Each runtime has a native control surface (Ray Train APIs, `torchrun`, DeepSpeed launcher flags). Exposing those natives north-bound would force cost dashboards, resume harnesses, and CI to speak N dialects.

We already solved this for inference with [ADR-001](./001-unified-model-serving-contract.md). Training needs the same discipline: one contract, three backends.

## Decision

Adopt **one** backend-agnostic training job contract in [`contracts/training-job-contract/`](../../contracts/training-job-contract/):

| Artifact | Role |
|----------|------|
| `TrainingJobSpec` | Dataset ref, model config (`reference-tiny-llm`), hyperparameters, distributed topology, `cpu_dev_mode` |
| `TrainingJobResult` | Checkpoint path, `metrics.json` (loss curve, samples/sec, steps/sec, wall-clock), resume metadata |

Every training backend under `training/{ray-train,fsdp-ddp,deepspeed}/` **must** accept a schema-valid spec and emit a schema-valid result. Native launchers may exist only *behind* the adapter; they are not the platform contract.

Optional local status HTTP (host ports **9011–9013**) exposes Prometheus-compatible `/metrics` and `/health` during a run; it does not replace the file artifacts as the contract of record.

Contract changes update OpenAPI + JSON Schema + tests together.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Per-backend public APIs | Cost/resume/CI become N×N adapters |
| Reuse `model-contract` `/v1/infer` | Wrong lifecycle; training is a job, not a request |
| Hash-pin checkpoints as the contract | Conflicts with ADR-009 structural verification |

## Consequences

**Gains**

- Cost-exporter, resume tests, and CI target one schema.
- Backends stay swappable behind the same north-bound surface.

**Trade-offs (accepted)**

- Backend-native knobs (DeepSpeed ZeRO stage details, Ray Tune search spaces) stay adapter-internal until promoted via a new ADR.

## Compliance

- New training backends: implement the OpenAPI/schemas; ship `cpu_dev_mode: true` defaults.
- `check-adr-gate.sh` maps `training/**` and `contracts/training-job-contract/**` → this ADR (with ADR-009 for GPU-cost-safety on training paths).
