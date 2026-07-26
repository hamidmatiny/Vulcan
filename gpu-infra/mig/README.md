# gpu-infra/mig

MIG (Multi-Instance GPU) partitioning profiles for Vulcan GPU nodes. Profiles are applied by the NVIDIA GPU Operator **migManager** (see [`../gpu-operator/`](../gpu-operator/)) — never by CI ([ADR-002](../../docs/adr/002-gpu-cost-safety-policy.md)).

Decision record: [ADR-003 — MIG partitioning strategy](../../docs/adr/003-mig-partitioning-strategy.md).

## Profiles

| Profile | File | Geometry (A100-class) | Intent |
|---------|------|------------------------|--------|
| `many-small-inference` | [`profiles/many-small-inference.yaml`](./profiles/many-small-inference.yaml) | `1g.5gb` × 7 | Pack many small inference replicas |
| `training-large-batch` | [`profiles/training-large-batch.yaml`](./profiles/training-large-batch.yaml) | `3g.40gb` + `4g.40gb` | Large KV / training-style batches |

Combined ConfigMap for validation / install: [`profiles/combined-configmap.yaml`](./profiles/combined-configmap.yaml).  
Helm overlay: [`values-mig.yaml`](./values-mig.yaml).

Activate on a node:

```bash
kubectl label node <gpu-node> nvidia.com/mig.config=many-small-inference --overwrite
# or
kubectl label node <gpu-node> nvidia.com/mig.config=training-large-batch --overwrite
```

## Trade-off: isolation & density vs memory ceiling

| | **Many small (1g.5gb × N)** | **Large partitions (3g/4g)** |
|--|----------------------------|-----------------------------|
| Isolation | Hardware-isolated slices; noisy-neighbor protection | Same, fewer slices |
| Packing density | High — many pods per physical GPU | Low — 1–2 heavy pods per GPU |
| Per-partition HBM | Hard ceiling (~5 GiB on 1g.5gb) | Much higher (~40 GiB class) |
| Failure domain | One slice OOM ≠ whole GPU | Larger blast radius per tenant |

Choose **many-small** when you run lots of small models or Triton model instances with modest footprints. Choose **training-large-batch** when a single replica needs a large KV cache or batch workspace and cannot fit in a 1g slice.

## Which phase 2–6 backends benefit most?

| Backend | MIG fit | Notes |
|---------|---------|-------|
| **Triton** (phase 4) | **Best** | Multi-model repository + dynamic batching maps cleanly onto many small isolated slices for multi-tenant inference |
| **KServe** (phase 6) | **Best** | Multi-tenant InferenceServices / canaries; schedule predictors onto MIG device plugin resources |
| **vLLM** (phase 5) | Selective | Large LLM KV often needs **training-large-batch** (or full GPU); 1g slices are usually too small |
| **BentoML / Ray Serve** (phases 2–3) | Moderate | Benefit from isolation, but less “native” multi-tenant packing than Triton/KServe |
| Compose CPU-dev | N/A | No MIG in local compose (ADR-002) |

## Validate

```bash
make validate-gpu-infra
```
