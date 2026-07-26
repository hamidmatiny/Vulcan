# gpu-infra/kueue

Multi-tenant **GPU admission** with [Kueue](https://kueue.sigs.k8s.io/). Two teams share the phase-7 GPU / MIG pool under explicit quotas and priorities.

CI validates manifests only — **never applies** ([ADR-002](../../docs/adr/002-gpu-cost-safety-policy.md)).  
Decision record: [ADR-004](../../docs/adr/004-multi-tenant-gpu-scheduling-with-kueue.md).

## Why this exists (two-team quota story)

Without a queueing layer, Kubernetes will schedule any pod that fits a node. That means a burst of **training** Jobs can fill every A100 while **inference** KServe predictors wait—or worse, never get MIG slices because nothing was reserved for them.

Kueue adds an **admission gate** in front of the scheduler:

```text
  team-inference namespace          team-training namespace
           │                                  │
           ▼                                  ▼
     LocalQueue lq-inference            LocalQueue lq-training
           │                                  │
           └──────────► ClusterQueues ◄───────┘
                        (cohort: vulcan-gpu-cohort)
                              │
                              ▼
                 ResourceFlavors → phase-7 nodes / MIG
```

| Team | Namespace | ClusterQueue | What they can consume (nominal) |
|------|-----------|--------------|----------------------------------|
| **Inference** | `team-inference` | `cq-inference` | **14×** `nvidia.com/mig-1g.5gb` (ADR-003 *many-small-inference*) + CPU/memory |
| **Training** | `team-training` | `cq-training` | **2×** `mig-3g.40gb` + **2×** `mig-4g.40gb` (ADR-003 *training-large-batch*) + **2** full GPUs |

Both queues are in one **cohort**, so unused capacity can be borrowed up to configured limits. **Inference-critical** workloads can reclaim capacity from lower-priority training (see WorkloadPriorityClasses). That is the value over “just PriorityClasses”: quotas are **device-flavor aware**, and work **waits in a queue** instead of hoping the scheduler gets lucky.

## Layout

```text
values-install.yaml     Helm values for the upstream Kueue chart (manual install)
chart/                  Vulcan queues, flavors, priorities
examples/               KServe InferenceService + training Job / Workload samples
policy/                 conftest (also run via gpu-infra/scripts/validate.sh)
```

## Priority classes

| WorkloadPriorityClass | Value | Role |
|-----------------------|-------|------|
| `vulcan-inference-critical` | 1000 | Online KServe / Triton predictors — may preempt training |
| `vulcan-inference-batch` | 500 | Batch inference |
| `vulcan-training` | 100 | Training / large-batch — preemptible |

## Examples

| File | Story |
|------|--------|
| [`examples/workload-kserve-inferenceservice.yaml`](./examples/workload-kserve-inferenceservice.yaml) | Phase-6 Triton InferenceService labeled into `lq-inference` + explicit Workload |
| [`examples/workload-training-job.yaml`](./examples/workload-training-job.yaml) | Forward-referenced training Job into `lq-training` (suspended until admitted) |

## Validate

```bash
make validate-gpu-infra
```

## Manual install (out of band)

```bash
helm upgrade --install kueue oci://registry.k8s.io/kueue/charts/kueue \
  --version 0.9.1 -n kueue-system --create-namespace \
  -f gpu-infra/kueue/values-install.yaml

helm upgrade --install vulcan-kueue ./gpu-infra/kueue/chart \
  -n kueue-system
```
