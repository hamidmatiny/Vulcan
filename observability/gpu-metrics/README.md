# observability/gpu-metrics

**Phase:** 17  
**ADR:** [ADR-008](../../docs/adr/008-self-hosted-cost-per-token-assumptions.md) (cost assumptions) · [ADR-002](../../docs/adr/002-gpu-cost-safety-policy.md) (no GPU in CI)

## Purpose

| Artifact | What it is |
|----------|------------|
| [`helm/dcgm-exporter-values.yaml`](./helm/dcgm-exporter-values.yaml) | **Real** GPU Operator / DCGM-Exporter values targeting phase-7 node labels/taints |
| [`prometheus/scrape-dcgm-cluster.yaml`](./prometheus/scrape-dcgm-cluster.yaml) | Cluster Prometheus scrape snippet for DCGM |
| [`synthetic-dcgm/`](./synthetic-dcgm/) | **Synthetic** DCGM-shaped metrics for CPU compose/CI (`data_source=synthetic_cpu_compose`) |

## Live vs synthetic vs real GPU

| Environment | GPU utilization series | Label honesty |
|-------------|------------------------|---------------|
| CPU compose / CI | Synthetic exporter | `data_source="synthetic_cpu_compose"` — **LIVE scrape**, sample values, **not** hardware |
| Phase-7 GPU node pools (manual apply) | NVIDIA DCGM Exporter via GPU Operator | Real `DCGM_FI_*` from GPUs |

CI never runs real DCGM (ADR-002). Grafana panels for compose use the synthetic series so wiring is testable end-to-end.

## Cluster install sketch (manual)

```bash
# After GPU Operator is installed on phase-7 pools (see gpu-infra/gpu-operator):
helm upgrade --install gpu-operator nvidia/gpu-operator \
  -f gpu-infra/gpu-operator/values-eks.yaml \
  -f observability/gpu-metrics/helm/dcgm-exporter-values.yaml \
  # ... never in CI
```

Merge the scrape snippet into your cluster Prometheus (or Prometheus Operator ServiceMonitor).
