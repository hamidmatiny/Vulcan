# ADR 003 — MIG partitioning strategy

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 7 (gpu-infra MIG + GPU Operator)

## Context

Vulcan serves multiple tenants and backends (BentoML, Ray Serve, Triton, vLLM, KServe) on shared NVIDIA GPUs. Full-GPU allocation wastes capacity for small inference replicas; unconstrained time-slicing weakens isolation. MIG gives hardware-partitioned GPU instances with separate memory and compute, at the cost of a fixed per-slice memory ceiling and fewer large jobs per card.

We need a small, documented set of profiles that operators can select per node pool — validated in CI as manifests, applied only out of band ([ADR-002](./002-gpu-cost-safety-policy.md)).

## Decision

Adopt **two named MIG profiles** (A100-class geometries), managed by GPU Operator `migManager` and selected via node label `nvidia.com/mig.config`:

| Profile | Geometry | Primary use |
|---------|----------|-------------|
| `many-small-inference` | `1g.5gb` × 7 | Multi-tenant small inference; maximize packing density |
| `training-large-batch` | `3g.40gb` + `4g.40gb` | Large-batch / large-KV workloads needing higher HBM per tenant |

Defaults:

- Cluster install leaves MIG **disabled** (`all-disabled`) until a node is labeled.
- Device plugin uses **`migStrategy: mixed`** so non-MIG and MIG nodes can coexist.
- EKS GPU node groups are labeled/tainted for GPU scheduling (see `infra/terraform`); profile choice is a second label on the node.

**Backend affinity (who benefits most):**

1. **Triton** and **KServe** — first-class for `many-small-inference` (multi-model / multi-InferenceService tenancy).
2. **vLLM** — prefer `training-large-batch` or full GPU when KV cache exceeds 1g ceilings.
3. **BentoML / Ray Serve** — optional isolation; not the primary MIG packing story.

Profiles live under [`gpu-infra/mig/`](../../gpu-infra/mig/); Operator values under [`gpu-infra/gpu-operator/`](../../gpu-infra/gpu-operator/).

## Alternatives considered

| Option | Why not |
|--------|---------|
| Time-slicing only | Weaker isolation; harder multi-tenant SLOs for inference |
| Single profile for all nodes | Forces either OOM on large models or wasted capacity on small ones |
| Full GPU per pod always | Simple but poor density and cost for small Triton/KServe replicas |
| Auto-MIG from utilization | Operationally complex; deferred until metrics-driven autoscaling matures |

## Consequences

**Gains**

- Clear operator knobs: two profiles, documented trade-offs.
- Triton/KServe multi-tenant packing without sharing a full GPU address space.
- CI can conftest profile ConfigMaps without attaching GPUs.

**Trade-offs (accepted)**

- 1g slices cannot run large LLM KV — those workloads must use the large profile or non-MIG nodes.
- Reconfiguring MIG drains GPU clients on the node (migManager behavior).
- Geometries are A100-oriented; other SKUs need a follow-on profile ADR.

## Compliance

- New MIG profiles: add YAML under `gpu-infra/mig/profiles/`, update `values-mig.yaml`, extend ADR-003 or add a follow-on ADR.
- Changes under `gpu-infra/` require ADR-002 **and** ADR-003 present (CI adr-gate).
- Never apply GPU Operator / MIG from GitHub Actions.
