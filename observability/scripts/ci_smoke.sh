#!/usr/bin/env bash
# Smoke: Prometheus targets up + dashboard query has data + at least one Tempo trace.
set -euo pipefail

PROM_URL="${PROM_URL:-http://127.0.0.1:9008}"
GRAFANA_URL="${GRAFANA_URL:-http://127.0.0.1:9009}"
GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:9007}"
TEMPO_URL="${TEMPO_URL:-http://127.0.0.1:9010}"

echo "==> wait prometheus ready"
for _ in $(seq 1 60); do
  if curl -fsS "${PROM_URL}/-/ready" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS "${PROM_URL}/-/ready" >/dev/null

echo "==> assert scrape targets up (bentoml, ray-serve, gateway, cost-exporter)"
ok_targets=0
for _ in $(seq 1 60); do
  if curl -fsS "${PROM_URL}/api/v1/targets?state=active" | python3 -c '
import json, sys
data = json.load(sys.stdin)
active = data["data"]["activeTargets"]
by_job = {}
for t in active:
    job = t["labels"].get("job", "")
    by_job.setdefault(job, []).append(t.get("health"))
need = ("bentoml", "ray-serve", "gateway", "cost-exporter")
for job in need:
    healths = by_job.get(job) or []
    if not any(h == "up" for h in healths):
        raise SystemExit(1)
print("OK targets", {k: by_job[k] for k in need})
'; then
    ok_targets=1
    break
  fi
  sleep 2
done
[[ "${ok_targets}" -eq 1 ]] || { echo "scrape targets not up in time" >&2; exit 1; }

echo "==> generate traffic through gateway (creates metrics + traces)"
for i in 1 2 3; do
  curl -fsS -X POST "${GATEWAY_URL}/v1/infer" \
    -H 'content-type: application/json' \
    -d "{\"request_id\":\"obs-smoke-${i}\",\"modality\":\"llm\",\"model_id\":\"reference-tiny-llm\",\"input\":{\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":8,\"temperature\":0}}" \
    >/dev/null
done
sleep 10

echo "==> Prometheus query used by Grafana latency panel returns data"
ok_q=0
for _ in $(seq 1 30); do
  if curl -fsS --get "${PROM_URL}/api/v1/query" \
    --data-urlencode "query=histogram_quantile(0.95, sum by (backend, le) (rate(vulcan_infer_latency_seconds_bucket[5m])))" \
    | python3 -c '
import json, sys
data = json.load(sys.stdin)
assert data.get("status") == "success", data
result = data["data"]["result"]
assert len(result) > 0, "dashboard latency query returned no series"
print("OK series", [(r["metric"].get("backend"), r["value"][1]) for r in result[:8]])
'; then
    ok_q=1
    break
  fi
  sleep 2
done
[[ "${ok_q}" -eq 1 ]] || { echo "latency query empty" >&2; exit 1; }

echo "==> cost-exporter series present"
curl -fsS --get "${PROM_URL}/api/v1/query" \
  --data-urlencode "query=vulcan_routing_latency_p95_ms" \
  | python3 -c '
import json, sys
data = json.load(sys.stdin)
assert data["data"]["result"], "expected vulcan_routing_latency_p95_ms from cost-exporter"
print("OK cost-exporter", len(data["data"]["result"]), "series")
'

echo "==> Grafana health"
curl -fsS "${GRAFANA_URL}/api/health" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("database")=="ok", d; print("OK grafana", d)'

echo "==> Tempo has at least one trace"
found=0
for _ in $(seq 1 45); do
  for url in \
    "${TEMPO_URL}/api/search?limit=20" \
    "${TEMPO_URL}/api/search?tags=service.name%3Dgateway&limit=10" \
    "${TEMPO_URL}/api/search?q=%7Bresource.service.name%3D%22gateway%22%7D&limit=10"
  do
    if curl -fsS "${url}" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("traces") else 1)'; then
      curl -fsS "${url}" | python3 -c '
import json,sys
d=json.load(sys.stdin)
traces=d.get("traces") or []
print("OK traces", len(traces), "sample", traces[0].get("rootServiceName"), traces[0].get("rootTraceName"))
'
      found=1
      break 2
    fi
  done
  sleep 2
done
[[ "${found}" -eq 1 ]] || { echo "no Tempo traces found" >&2; exit 1; }

echo "OK observability ci_smoke"
