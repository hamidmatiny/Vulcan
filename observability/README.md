# observability

**Path:** `observability/`  
**Phases:** 14 · 17  
**Ports:** **9008** Prometheus · **9009** Grafana · **9010** Tempo (query)

## Purpose

CPU-mode observability for Vulcan serving + the phase-13 gateway:

- **Traces** — OpenTelemetry (OTLP → collector → Tempo); gateway propagates `traceparent` into the selected backend
- **Metrics** — Prometheus scrapes each backend’s existing phase-0 `GET /metrics` (`vulcan_infer_*`); no parallel metric model
- **Dashboards** — Grafana “Vulcan Serving (CPU compose)”
- **Cost** — `cost-exporter` re-reads `benchmark/results/*.json` + Bedrock `pricing-reference.json` (ADR-006) and documented `$/GPU-hour` assumptions (ADR-008) for **cost-per-token**
- **GPU** — real DCGM Helm/scrape under [`gpu-metrics/`](./gpu-metrics/) for phase-7 pools; **synthetic** DCGM-shaped exporter in compose/CI
- **Alerts** — Prometheus rules → Alertmanager (null sink locally)

## Live vs LIVE-SYNTHETIC vs PLACEHOLDER (ADR-002)

| Panel | Source | CPU compose |
|-------|--------|-------------|
| Latency p95 / throughput / error rate | `vulcan_infer_*` scrapes | **LIVE** |
| Contract `/health` | blackbox → `probe_success` | **LIVE** |
| Routing catalog latency | cost-exporter ← benchmark/pricing JSON | **LIVE** |
| Cost / inference + **cost-per-token** | cost-exporter (Bedrock pricing-reference **or** ADR-008 formula) | **LIVE** (documented assumptions, not invoices) |
| GPU utilization | `DCGM_FI_DEV_GPU_UTIL{data_source="synthetic_cpu_compose"}` | **LIVE-SYNTHETIC** — scraped sample series, **not** real GPU |
| Real DCGM on GPU nodes | `gpu-metrics/helm` + cluster scrape snippet | **Not in compose** — manual cluster only |

There is **no** remaining `placeholder_cpu_compose` GPU panel. Real hardware DCGM still requires applying phase-7 pools (ADR-002).

## How to run

```bash
make up-observability
# includes cost-exporter + synthetic-dcgm
```

- Grafana: http://127.0.0.1:9009
- Prometheus: http://127.0.0.1:9008

## CI smoke

`observability/scripts/ci_smoke.sh` asserts scrape targets (including `cost-exporter` + `synthetic-dcgm`), latency query data, **`vulcan_estimated_cost_usd_per_token`**, and a Tempo trace.

## Layout

```text
observability/
  prometheus/          scrape + alert rules
  blackbox/            /health probe module
  alertmanager/        local null receiver
  otel/                collector config
  tempo/               local trace store
  grafana/             provisioning + dashboards
  cost-exporter/        routing cost/latency + cost-per-token (ADR-006/008)
  gpu-metrics/         real DCGM Helm/scrape + synthetic-dcgm for compose
  scripts/ci_smoke.sh
```
