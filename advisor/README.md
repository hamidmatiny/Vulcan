# advisor/ — LangGraph tool-grounded serving advisor (ADR-014)

CLI/library graph that answers routing/cost questions using **only** real local
data sources. Non-fabrication is enforced in CI.

## Tools

| Node | Source |
|------|--------|
| `query_prometheus` | PromQL → `http://127.0.0.1:9008` (same family as `observability/scripts/ci_smoke.sh`) |
| `read_benchmark_results` | `benchmark/results/*-cpu.json` |
| `query_routing_history` | Live gateway `POST /v1/infer` → `routing` object |
| `recommend` | Template (+ optional local GPT-2-small commentary) |

## Run

```bash
# Offline unit tests (benchmarks + grounding helpers; no compose)
make test-advisor

# Full graph against local stack (Prometheus + gateway + at least one backend)
docker compose up -d bentoml gateway prometheus cost-exporter
export VULCAN_ADVISOR_LIVE=1
make test-advisor-live
PYTHONPATH=. advisor/.venv/bin/python -m advisor.run \
  "which backend should I use for lowest cost per token right now?"
```

## Env

| Var | Default | Meaning |
|-----|---------|---------|
| `VULCAN_PROM_URL` | `http://127.0.0.1:9008` | Prometheus |
| `VULCAN_GATEWAY_URL` | `http://127.0.0.1:9007` | Gateway |
| `VULCAN_MODELS_DIR` | `models/artifacts` | Pinned LLM root |
| `VULCAN_ADVISOR_LIVE` | unset | Enable live Prom/gateway tests |

No new host port. Hosted LLM mode is manual only — see
[`docs/runbooks/advisor-hosted-llm.md`](../docs/runbooks/advisor-hosted-llm.md).
