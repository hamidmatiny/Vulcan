# Vulcan demo script (~5 minutes)

Commands below are the ones that exist in this repo today. Prerequisites: Docker, `make`, `curl`, `python3`, and phase-1 model artifacts (`make models-export` once).

## 0. Bring up the CPU stack + gateway + Grafana

```bash
# From repo root
make models-export   # skip if models/artifacts already present
make up-observability
# Starts bentoml + ray-serve + gateway + Prometheus/Grafana/Tempo (ports 9000/9002/9007/9008/9009/9010)
make wait-for-health WAIT_PORT=9007
```

Open Grafana: [http://127.0.0.1:9009](http://127.0.0.1:9009) → folder **Vulcan** → dashboard **Vulcan Serving (CPU compose)**.

## 1. Hit the gateway (contract surface)

```bash
curl -fsS http://127.0.0.1:9007/health | python3 -m json.tool
curl -fsS -X POST http://127.0.0.1:9007/v1/infer \
  -H 'content-type: application/json' \
  -d '{
    "request_id":"demo-1",
    "modality":"llm",
    "model_id":"reference-tiny-llm",
    "input":{"messages":[{"role":"user","content":"hello from vulcan"}],"max_tokens":16,"temperature":0}
  }' | python3 -m json.tool
```

Note `routing.selected_backend` and `routing.candidates` — selection uses recorded `benchmark/results/*-cpu.json` (ADR-006).

## 2. Steer routing with constraints

Lowest recorded LLM p95 among compose backends is typically **ray-serve**, then **bentoml**. Force bentoml:

```bash
curl -fsS -X POST http://127.0.0.1:9007/v1/infer \
  -H 'content-type: application/json' \
  -d '{
    "request_id":"demo-2",
    "modality":"llm",
    "model_id":"reference-tiny-llm",
    "input":{"messages":[{"role":"user","content":"prefer bentoml"}],"max_tokens":8,"temperature":0},
    "constraints":{"preferred_backend":"bentoml"}
  }' | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["routing"]["selected_backend"], d["routing"].get("attempts"))'
```

Latency ceiling that still admits bentoml/ray but excludes slower catalog entries:

```bash
curl -fsS -X POST http://127.0.0.1:9007/v1/infer \
  -H 'content-type: application/json' \
  -d '{
    "request_id":"demo-3",
    "modality":"llm",
    "model_id":"reference-tiny-llm",
    "input":{"messages":[{"role":"user","content":"latency cap"}],"max_tokens":8,"temperature":0},
    "constraints":{"max_latency_ms":500}
  }' | python3 -c 'import json,sys; d=json.load(sys.stdin); print("selected=", d["routing"]["selected_backend"]); print("candidates=", [(c["backend"], c.get("latency_p95_ms")) for c in d["routing"]["candidates"]])'
```

## 3. Kill a backend and show explainable fallback

```bash
# Same script CI uses (stops the selected compose service, re-infers, asserts fallback + unhealthy attempt)
GATEWAY_URL=http://127.0.0.1:9007 bash gateway/scripts/ci_fallback.sh
```

Expect `routing.fallback=true` and an `attempts[]` entry with `outcome=unhealthy`. The script restarts the stopped service when done.

## 4. Glance at live metrics in Grafana

```bash
# Confirm Prometheus still scrapes gateway /metrics
curl -fsS 'http://127.0.0.1:9008/api/v1/query?query=up{job="gateway"}' | python3 -m json.tool | head -40
```

In Grafana, the **LIVE** panels (latency / throughput / error rate / health) should move after the curls above. **PLACEHOLDER** GPU panels stay labeled `data_source=placeholder_cpu_compose` (ADR-002).

## 5. Tear down (optional)

```bash
make down
```
