#!/usr/bin/env bash
# Kill the lowest-latency compose backend and prove gateway fallback surfaces a reason.
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:9007}"
COMPOSE="${COMPOSE:-docker compose}"

payload='{"request_id":"fallback-1","modality":"llm","model_id":"reference-tiny-llm","input":{"messages":[{"role":"user","content":"hi"}],"max_tokens":8,"temperature":0}}'

echo "==> baseline infer via gateway"
base="$(curl -fsS -X POST "${GATEWAY_URL}/v1/infer" -H 'content-type: application/json' -d "${payload}")"
selected="$(printf '%s' "${base}" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "routing" in d; print(d["routing"]["selected_backend"])')"
echo "selected=${selected}"

case "${selected}" in
  bentoml) kill_svc=bentoml ;;
  ray-serve) kill_svc=ray-serve ;;
  triton) kill_svc=triton ;;
  vllm) kill_svc=vllm ;;
  *) echo "unexpected selected backend: ${selected}" >&2; exit 1 ;;
esac

echo "==> stopping ${kill_svc} to force fallback"
${COMPOSE} stop "${kill_svc}"
# Give the gateway a moment; health probe should fail fast.
sleep 2

echo "==> infer after kill"
after="$(curl -fsS -X POST "${GATEWAY_URL}/v1/infer" -H 'content-type: application/json' -d "${payload}")"
printf '%s' "${after}" | python3 -c '
import json, sys
d = json.load(sys.stdin)
r = d["routing"]
assert r.get("fallback") is True, r
assert r["selected_backend"], r
attempts = r.get("attempts") or []
assert any(a.get("outcome") == "unhealthy" for a in attempts), attempts
print("OK fallback", r["selected_backend"], "attempts", attempts)
'

echo "==> restarting ${kill_svc}"
${COMPOSE} start "${kill_svc}"
echo "OK ci_fallback"
