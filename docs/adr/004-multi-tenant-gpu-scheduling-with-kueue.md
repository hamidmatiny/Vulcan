# ADR 004 — Multi-tenant GPU scheduling with Kueue

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 8 (gpu-infra/kueue)

## Context

Phase 7 introduced EKS GPU node groups, the NVIDIA GPU Operator, and two MIG profiles ([ADR-003](./003-mig-partitioning-strategy.md)). Multiple **teams** (online inference vs training / large-batch) must share that pool without:

1. One team permanently starving the other.
2. Training jobs displacing latency-sensitive KServe predictors without policy.
3. Operators hand-editing PriorityClasses and hoping the kube-scheduler alone enforces fair GPU use.

Raw Kubernetes PriorityClasses + ResourceQuotas are insufficient: they do not model **queueing**, **cohort borrowing**, or **admission against heterogeneous device flavors** (full GPU vs `mig-1g.5gb` vs `mig-3g.40gb`).

## Decision

Adopt **[Kueue](https://kueue.sigs.k8s.io/)** as the multi-tenant admission control plane for Vulcan GPU workloads:

| Object | Vulcan use |
|--------|------------|
| `ResourceFlavor` | Maps to phase-7 node pools / MIG profiles (`mig-small`, `mig-large`, `gpu-full`) |
| `ClusterQueue` | Per-team nominal GPU/MIG quotas + cohort membership |
| `LocalQueue` | Namespaced entry point (`lq-inference`, `lq-training`) |
| `WorkloadPriorityClass` | Inference-critical > inference-batch > training |
| `Workload` | Admission unit for KServe predictors and training Jobs |

**Two teams (initial):**

1. **Inference** — `cq-inference` / `lq-inference` — nominal quota on `nvidia.com/mig-1g.5gb` (many-small-inference).
2. **Training** — `cq-training` / `lq-training` — nominal quota on `nvidia.com/mig-3g.40gb` / `mig-4g.40gb` plus limited full GPUs.

Both ClusterQueues join cohort `vulcan-gpu-cohort` so unused capacity can be borrowed under configured limits.

**Quota starvation & preemption:**

- **Nominal quotas** guarantee each team a floor; borrowing is capped (`borrowingLimit`).
- **Preemption**: `withinClusterQueue: LowerPriority`; inference ClusterQueue may `reclaimWithinCohort: Any` so online serving can reclaim borrowed capacity from training.
- **WorkloadPriorityClass** values ensure `vulcan-inference-critical` preempts `vulcan-training`.
- Workloads that do not fit wait in queue (FIFO / BestEffortFIFO) instead of partial-scheduling into OOM.

Manifests: [`gpu-infra/kueue/`](../../gpu-infra/kueue/). CI validates only ([ADR-002](./002-gpu-cost-safety-policy.md)).

## Alternatives considered

| Option | Why not |
|--------|---------|
| Raw PriorityClass only | No queueing; no MIG-flavor quotas; starvation when low-prio pods already running |
| Namespace ResourceQuota only | Static caps; no borrowing/cohort; poor fit for heterogeneous MIG resources |
| Volcano / YuniKorn as default | Capable, but Kueue is the Kubernetes-SIG-aligned batch admission layer and integrates cleanly with Job + emerging KServe patterns |
| One shared ClusterQueue for all teams | Simpler ops, weaker multi-tenant guarantees and accountability |

## Consequences

**Gains**

- Clear two-team story reviewers can reason about (inference vs training).
- MIG-aware quotas align with ADR-003 profiles.
- Preemption policy favors online inference without forbidding training.

**Trade-offs (accepted)**

- Additional CRDs and operator to run (Kueue).
- KServe admission patterns evolve by Kueue version; examples document the intended labels/Workloads.
- Fair-share tuning (borrow limits) will need production metrics later.

## Compliance

- Changes under `gpu-infra/kueue/` require **ADR-004** (and ADR-002) via CI adr-gate.
- New teams/queues: update chart values, examples, and this ADR (or a follow-on).
- Never apply Kueue or queues from GitHub Actions.
