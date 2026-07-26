# ADR 005 — Spot GPU strategy

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 9 (autoscaling/karpenter, autoscaling/checkpointing)

## Context

GPU nodes dominate Vulcan’s cloud cost. Spot capacity is often **50–70%+ cheaper** than on-demand for the same `g5` / `p4d` shapes, but AWS can reclaim instances with ~2 minutes notice. Phase 7–8 already label nodes for MIG / Kueue flavors; phase 9 must decide **which workloads may land on spot** and what contract makes interruption survivable.

Running all GPU capacity as on-demand is simple and expensive. Running all capacity as spot without checkpointing and disruption budgets is cheap until a reclaim wave deletes every replica of a predictor or resets multi-hour training.

## Decision

### Capacity mix (Karpenter)

Provision GPU NodePools with **mixed `karpenter.sh/capacity-type`** (`spot` + `on-demand`), wired to the **same labels** as phase 7 Terraform and phase 8 ResourceFlavors (`vulcan.dev/gpu`, `vulcan.dev/mig`, `vulcan.dev/gpu-pool`, `nvidia.com/mig.config`). Do not invent a parallel labeling scheme.

| Workload class | Preferred capacity | Rationale |
|----------------|-------------------|-----------|
| Real-time / online inference (KServe predictors, latency SLOs) | **On-demand** (spot only as overflow) | Spot reclaim → cold start / replica loss; checkpointing does not help in-flight HTTP |
| Batch inference | Spot OK if job is restartable or queued | Throughput over latency |
| Training / fine-tune / large-batch (Kueue training queue) | **Spot-first** | Long-running; cost dominates; must implement checkpoint-resume |

Consolidation: `WhenEmptyOrUnderutilized` with documented **disruption budgets** (e.g. 20% / max 1 node; tighter for inference) so Karpenter-initiated drains cannot remove all replicas of a backend at once. Budgets do not block AWS spot reclaim — see checkpoint contract.

Manifests: [`autoscaling/karpenter/`](../../autoscaling/karpenter/).

### Checkpoint-resume contract

Long-running GPU jobs that run on spot (or are Kueue-preemptible) **must**:

1. Persist progress on **SIGTERM** (and preferably periodically).
2. **Resume** from the last completed step on restart (PVC / object store).
3. Treat Kueue preemption ([ADR-004](./004-multi-tenant-gpu-scheduling-with-kueue.md)) and Karpenter/AWS spot SIGTERM as the **same** signal path.

Reference implementation (phase-1 GPT-2 fine-tune path, CPU-simulable): [`autoscaling/checkpointing/`](../../autoscaling/checkpointing/). Phase 12 training Job should adopt this contract with real HF/accelerate checkpoints.

### Explicitly not safe on spot

- **Real-time inference** with customer-facing latency SLOs — prefer on-demand NodePool `vulcan-gpu-inference` / `gpu-pool=inference`.
- Single-replica critical predictors without PDB + multi-AZ on-demand capacity.
- Any job that cannot checkpoint within the termination grace period.

### Explicitly safe (with checkpoint-resume)

- Training / fine-tuning Jobs on `mig-large` / spot-heavy pools.
- Batch offline scoring that is idempotent or checkpointed.
- Workloads already designed for Kueue preemption.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Spot-only for all GPU | Unacceptable risk for online inference HA |
| On-demand-only | Leaves large cost on the table for training |
| Separate label taxonomy for Karpenter | Diverges from Kueue flavors / MIG profiles; scheduling bugs |
| Rely on disruption budgets alone | Budgets do not stop AWS reclaim; training still needs checkpoints |

## Consequences

**Gains**

- Clear cost vs risk split reviewers can enforce in PRs and conftest.
- Shared label story across Terraform, GPU Operator/MIG, Kueue, and Karpenter.
- Testable checkpoint contract without GPU CI spend ([ADR-002](./002-gpu-cost-safety-policy.md)).

**Trade-offs (accepted)**

- Operators must size `terminationGracePeriod` and storage for checkpoints.
- Inference overflow onto spot still needs PDBs and multi-replica topology.
- Spot-to-spot consolidation feature flags may be required later for deeper savings.

## Compliance

- Changes under `autoscaling/**` require **ADR-005** via CI adr-gate.
- Karpenter manifests: validate-only in CI (helm template + kubeconform + conftest).
- Checkpoint package: real pytest in CI (SIGTERM simulation, no GPU).
