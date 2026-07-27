# ADR 008 — Self-hosted cost-per-token assumptions

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 17 (`observability/cost-exporter/`, `observability/gpu-metrics/`)

## Context

ADR-006 leaves self-hosted `$/1k` **null** because `benchmark/results/*.json` record latency/throughput, not dollars. Phase-14’s cost-exporter therefore only emitted Bedrock cost from `pricing-reference.json`. Operators still want a **cost-per-token** panel for bentoml/ray/triton/vllm without inventing a second Bedrock-style price list or fabricating GPU invoice data.

## Decision

### Single cost model (extend ADR-006 sources — do not fork)

| Backend class | Cost-per-token source |
|---------------|----------------------|
| Bedrock | Existing `bedrock-gateway/pricing-reference.json` (`input`/`output` `$/1k` → per-token = blend/1000 or explicit input/output as documented in exporter) |
| Self-hosted (compose backends) | `throughput_rps` from `benchmark/results/*-cpu.json` **×** documented assumptions in `observability/cost-exporter/gpu-hour-assumptions.json` |

### Formula (self-hosted)

\[
\text{tokens/s} = \text{throughput\_rps} \times T_{\text{req}}
\]

\[
\$/\text{token} = \frac{\$/\text{GPU-hour}}{3600 \times \text{tokens/s}}
\]

where:

- `throughput_rps` comes from the recorded k6 artifact (same files the gateway catalog reads).
- `$/GPU-hour` is looked up for an instance type that **already appears** in `infra/terraform/environments/gpu-eks/main.tf` (`g5.xlarge`, `g5.2xlarge`, `p4d.24xlarge`) — no new instance families.
- \(T_{\text{req}}\) = `assumed_tokens_per_request` in the assumptions file (default **16**, matching short CI k6 `max_tokens` shapes).

Default mapping: self-hosted inference → **`g5.xlarge`** (`gpu_inference` pool).

### Labeling

The assumptions file MUST carry `source: static_reference_assumption` and a **disclaimer** in the same spirit as Bedrock’s `pricing-reference.json`. Metrics MUST set `source` labels that name the assumptions file and/or benchmark path — never imply CloudWatch/Cost Explorer.

### Explicitly not claimed

- Not validated against a real AWS invoice or Cost Explorer export.
- Not a substitute for FinOps allocation on MIG (`p4d.24xlarge` listed for completeness; default inference math uses `g5.xlarge`).
- CPU-compose throughput is **not** GPU capacity — using it yields a **planning** cost-per-token for dashboards, not a production SLO.

## Consequences

- Grafana can show self-hosted and Bedrock cost-per-token on one dashboard without a second pricing ontology.
- Changing node types in Terraform without updating `gpu-hour-assumptions.json` is a documentation drift risk — CI does not scrape AWS prices (ADR-002).
- ADR gate: changes under `observability/gpu-metrics/**` or `observability/cost-exporter/gpu-hour-assumptions.json` require this ADR.

## Compliance

`check-adr-gate.sh` maps those paths → `008-self-hosted-cost-per-token-assumptions.md`.
