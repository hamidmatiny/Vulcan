# observability

**Path:** `observability/`  
**Phase:** 14  
**Ports:** **9008** Prometheus · **9009** Grafana · **9010** Tempo (query)

## Purpose

CPU-mode observability for Vulcan serving + the phase-13 gateway:

- **Traces** — OpenTelemetry (OTLP → collector → Tempo); gateway propagates `traceparent` into the selected backend
- **Metrics** — Prometheus scrapes each backend’s existing phase-0 `GET /metrics` (`vulcan_infer_*`); no parallel metric model
- **Dashboards** — Grafana “Vulcan Serving (CPU compose)”
- **Cost panel** — `cost-exporter` re-reads `benchmark/results/*.json` + `bedrock-gateway/pricing-reference.json` (same sources as gateway ADR-006)
- **Alerts** — Prometheus rules → Alertmanager (null sink locally): contract `/health` (same semantics as the gateway circuit breaker) + elevated infer error rate

## Live vs PLACEHOLDER panels (ADR-002)

| Panel | Source | CPU compose |
|-------|--------|-------------|
| Latency p95 / throughput / error rate | `vulcan_infer_*` scrapes | **LIVE** |
| Contract `/health` | blackbox → `probe_success` | **LIVE** |
| Routing catalog latency + Bedrock $/inference | cost-exporter (repo JSON) | **LIVE** |
| GPU utilization | `vulcan_gpu_utilization_ratio{data_source="placeholder_cpu_compose"}` | **PLACEHOLDER** — not DCGM / not real GPU |

Self-hosted backends have **no** recorded `$/1k` in-repo (ADR-006). Cost-per-inference series appear for **Bedrock pricing-reference** only; we do not invent $0 for bentoml/ray/triton/vllm.

## KServe

KServe does not own a separate `/metrics` binary in this repo — it schedules adapter images. Scrape the underlying bentoml/ray/triton/vllm (or port-forward `:9005`) the same way. No kserve-specific scrape target is registered in the CPU compose file.

## How to run

```bash
# Backends + gateway + full obs stack
docker compose up -d --build bentoml ray-serve gateway \
  otel-collector tempo prometheus alertmanager blackbox cost-exporter grafana

# Or:
make up-observability
```

- Grafana: http://127.0.0.1:9009 (anonymous Viewer; admin/admin)
- Prometheus: http://127.0.0.1:9008
- Tempo search: http://127.0.0.1:9010
- Generate a traced request: `curl` gateway `/v1/infer`, then Grafana → Explore → Tempo (`service.name=gateway`)

## CI smoke

`observability/scripts/ci_smoke.sh` asserts scrape targets are **up**, the latency dashboard query returns series, and Tempo has at least one trace after traffic through the gateway.

## Layout

```text
observability/
  prometheus/          scrape + alert rules
  blackbox/            /health probe module
  alertmanager/        local null receiver
  otel/                collector config
  tempo/               local trace store
  grafana/             provisioning + dashboards
  cost-exporter/        routing cost/latency + GPU placeholders
  scripts/ci_smoke.sh
```
