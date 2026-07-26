# ADR 006 — Routing policy

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 13 (`gateway/`)

## Context

Vulcan has multiple contract-conformant backends (self-hosted and managed). Callers should not hard-code a backend URL. The gateway must pick among them using **recorded** data already in the repo — not invented defaults — and must remain a **conformant** phase-0 backend itself.

## Decision

### Data sources (authoritative)

| Backend class | Latency | Cost ($/1k tokens) |
|---------------|---------|---------------------|
| bentoml, ray-serve, triton, vllm | `benchmark/results/*-cpu.json` → `metrics.latency_ms.p95` | **None recorded** — left null |
| bedrock | `bedrock-gateway/pricing-reference.json` → `typical_latency_ms.p95` | blended `(input+output)/2` from that file (`source=static_reference`) |
| kserve | — | — |
| sagemaker | — | — |

**kserve** and **sagemaker** appear in the catalog but are **`AutoSelect=false`** until comparable recorded artifacts exist. Reasons are returned in `routing.attempts` when skipped. Prefer measuring a real KServe shim URL into `benchmark/results/` before enabling auto-select; do not fabricate SageMaker latency/cost.

### Selection algorithm (`adr-006-v1`)

1. **Modality filter** — drop backends that do not list the request modality.
2. **URL filter** — drop backends with empty base URL.
3. **Auto-select filter** — drop `AutoSelect=false` unless `constraints.preferred_backend` matches (soft force still requires health).
4. **Latency data** — drop backends with null latency unless preferred_backend forces them.
5. **Hard constraints**
   - `max_latency_ms`: require `latency_p95_ms ≤ max` when latency is known.
   - `max_cost_usd_per_1k_tokens`: require known cost ≤ max. Backends with **null cost** (self-hosted) are **skipped** with detail `no_cost_data` — we do **not** invent $0.
   - `preferred_region` / `data_residency`: require case-insensitive match on backend region/residency.
6. **Score** remaining candidates (lower is better):

   \[
   score = \frac{w_L \cdot \hat{L} + w_C \cdot \hat{C}}{w_L + w_C}
   \]

   where \(\hat{L}\), \(\hat{C}\) are min-max normalized among the remaining pool using recorded p95 / $/1k. Defaults: \(w_L=0.7\), \(w_C=0.3\). If a dimension is missing for all remaining, its weight is treated as 0. `preferred_backend` subtracts `0.05` from score (soft preference only).
7. **Health / circuit break** — probe `GET {base}/health` in rank order. Require HTTP 200 and `status=="ok"`. On failure, record `attempts[].outcome=unhealthy` (or `circuit_open`), trip breaker after 2 consecutive failures (10s cooldown default), try next candidate (`fallback=true`).
8. **Proxy** — forward `/v1/infer` with `constraints` stripped; attach `routing` (decision) to the JSON response.

### Conflicting constraints

If the filtered pool is empty, return **502** `no_backend` with the full `routing` object (skips + reasons). No silent relaxation of hard constraints.

### Degradation with missing data

- No latency artifact → not auto-selected.
- No cost artifact → ignored for ranking unless a cost constraint is present (then skipped).
- Managed backends without URL → skipped (`base URL unset`).

## Alternatives considered

| Option | Why not |
|--------|---------|
| Hard-coded latency/cost tables in Go | Diverges from recorded CI artifacts; becomes fiction |
| Treat self-hosted cost as $0 | Invents a number the repo does not record |
| Always prefer vLLM | Ignores measured bentoml/ray latency advantages on CPU CI |

## Consequences

- Gateway stays explainable: every response can include `routing.attempts` / `candidates`.
- Adding a backend to auto-select means adding a real `benchmark/results/` (or pricing-reference) artifact — not editing magic constants.
- Contract optionally carries `constraints` (request) and `routing` (response); non-gateway backends ignore them.

## Compliance

Changes under `gateway/**` require **ADR-006** via CI adr-gate.
