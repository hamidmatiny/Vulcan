# gateway

**Path:** `gateway/`  
**Phase:** 13  
**Port:** **9007**  
**ADR:** [ADR-006 Routing policy](../docs/adr/006-routing-policy.md)

## Purpose

Go routing service that exposes the **same phase-0 contract** as every other backend (`/health`, `/metrics`, `/v1/infer`, `/v1/resources`) and selects among catalogued backends using **recorded** repo data:

- Latency: `benchmark/results/*-cpu.json` (`metrics.latency_ms.p95`) for bentoml / ray-serve / triton / vllm
- Bedrock cost + typical latency: `bedrock-gateway/pricing-reference.json` (static reference, not live)

Optional request `constraints` (`max_latency_ms`, `max_cost_usd_per_1k_tokens`, `preferred_region` / `data_residency`, `preferred_backend`) steer selection. Responses include a legible `routing` object (selected backend, ranked candidates, health/fallback attempts) — not a black box.

## Catalog honesty

| Backend | Auto-select? | Why |
|---------|--------------|-----|
| bentoml, ray-serve, triton, vllm | Yes (when URL set + benchmark present) | Real k6 artifacts in `benchmark/results/` |
| bedrock | Yes when `VULCAN_BEDROCK_URL` set | Pricing/latency from `pricing-reference.json` |
| **kserve** | **No** | No `benchmark/results` entry for the KServe shim; it wraps other backends — measure the shim before enabling |
| **sagemaker** | **No** | No comparable k6/`benchmark/results` artifact; we refuse to invent latency/cost. Use an explicit `preferred_backend=sagemaker` only after you publish a real measurement file |

## Local / compose

```bash
# Start backends + gateway
docker compose up -d --build bentoml ray-serve gateway
# or full stack including triton/vllm engines, then:
curl -sS http://127.0.0.1:9007/health
curl -sS http://127.0.0.1:9007/v1/infer -H 'content-type: application/json' -d '{
  "request_id":"g1","modality":"llm","model_id":"reference-tiny-llm",
  "input":{"messages":[{"role":"user","content":"hi"}],"max_tokens":16},
  "constraints":{"max_latency_ms":3000}
}'
```

## Tests

```bash
cd gateway && go test ./...
# Conformance (shared Python suite) against a running gateway:
VULCAN_BACKEND_URL=http://127.0.0.1:9007 make test-serving-common
```

## Circuit breaking

Unhealthy `/health` → try next-ranked backend; `routing.fallback=true` and `attempts` list the unhealthy reason. Breaker opens after consecutive failures (see ADR-006).

## Tracing

When `OTEL_EXPORTER_OTLP_ENDPOINT` is set (compose: `http://otel-collector:4318`), the gateway emits OTLP spans and injects W3C `traceparent` on proxied `/v1/infer` calls so backends continue the same trace (see [`observability/`](../observability/)).
