# karpenter

**Path:** `autoscaling/karpenter/`  
**Phase:** 9  
**ADR:** [ADR-005 Spot GPU strategy](../../docs/adr/005-spot-gpu-strategy.md)

## Purpose

Karpenter `NodePool` + `EC2NodeClass` manifests that provision GPU nodes with a **spot + on-demand** mix, consolidation, and disruption budgets. Node labels match phase 7–8 ResourceFlavors (not a parallel scheme).

## Label alignment (do not invent new keys)

| NodePool | Capacity | Labels (subset) | Matches |
|----------|----------|-----------------|---------|
| `vulcan-gpu-inference` | on-demand + spot | `vulcan.dev/gpu=true`, `vulcan.dev/gpu-pool=inference`, `nvidia.com/mig.config=all-disabled` | Kueue flavor `gpu-full` |
| `vulcan-gpu-mig-small` | spot + on-demand | `vulcan.dev/mig=many-small-inference`, `vulcan.dev/gpu-pool=mig-small` | Kueue `mig-small` / ADR-003 |
| `vulcan-gpu-mig-large` | spot + on-demand | `vulcan.dev/mig=training-large-batch`, `vulcan.dev/gpu-pool=mig-large` | Kueue `mig-large` / ADR-003 |

All pools taint `nvidia.com/gpu=true:NoSchedule` (same as Terraform GPU node groups).

## Disruption budget

`spec.disruption`:

- `consolidationPolicy: WhenEmptyOrUnderutilized`
- `consolidateAfter: 5m`
- `budgets`: default **20%** of nodes (or **1** node when the pool is small) for Empty / Underutilized / Drifted

Budgets rate-limit **Karpenter-initiated** drains so consolidation cannot empty every replica of a backend at once. AWS spot interruption is still host-driven; pair with [checkpointing](../checkpointing/) and pod PDBs for HA.

Inference NodePool uses a tighter **10% / 1 node** budget (real-time serving prefers on-demand — see ADR-005).

## Validate (CI / local)

```bash
make validate-autoscaling
# or
bash autoscaling/karpenter/scripts/validate.sh
```

ADR-002: **never apply** from GitHub Actions. Replace `role` / subnet / SG selectors in `chart/values.yaml` out-of-band before `kubectl apply`.

## Layout

```text
chart/           Helm chart (EC2NodeClass + NodePools)
policy/          conftest (label + budget gates)
scripts/validate.sh
```
