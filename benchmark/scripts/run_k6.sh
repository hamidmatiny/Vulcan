#!/usr/bin/env bash
# Run the Vulcan k6 harness (dockerized if local k6 is missing).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
MODEL_TYPE="${MODEL_TYPE:-llm}"
MODEL_ID="${MODEL_ID:-}"
VUS="${VUS:-5}"
DURATION="${DURATION:-15s}"
BACKEND_NAME="${BACKEND_NAME:-reference}"
RESULTS_OUT="${RESULTS_OUT:-benchmark/results/${BACKEND_NAME}-${MODEL_TYPE}.json}"

mkdir -p "$(dirname "$RESULTS_OUT")"

export BASE_URL MODEL_TYPE MODEL_ID VUS DURATION BACKEND_NAME RESULTS_OUT

K6_ARGS=(run benchmark/k6/infer.js)

if command -v k6 >/dev/null 2>&1; then
  echo "using local k6 → ${RESULTS_OUT}"
  # k6 writes via handleSummary relative to cwd
  env BASE_URL="$BASE_URL" MODEL_TYPE="$MODEL_TYPE" MODEL_ID="$MODEL_ID" \
      VUS="$VUS" DURATION="$DURATION" BACKEND_NAME="$BACKEND_NAME" \
      RESULTS_OUT="$RESULTS_OUT" \
      k6 "${K6_ARGS[@]}"
else
  echo "local k6 not found; using docker.io/grafana/k6"
  # Map host.docker.internal for macOS; Linux may need --add-host
  DOCKER_BASE_URL="$BASE_URL"
  if [[ "$BASE_URL" == *"127.0.0.1"* ]] || [[ "$BASE_URL" == *"localhost"* ]]; then
    DOCKER_BASE_URL="${BASE_URL/127.0.0.1/host.docker.internal}"
    DOCKER_BASE_URL="${DOCKER_BASE_URL/localhost/host.docker.internal}"
  fi
  docker run --rm \
    --add-host=host.docker.internal:host-gateway \
    -v "$ROOT:/work" -w /work \
    -e BASE_URL="$DOCKER_BASE_URL" \
    -e MODEL_TYPE="$MODEL_TYPE" \
    -e MODEL_ID="$MODEL_ID" \
    -e VUS="$VUS" \
    -e DURATION="$DURATION" \
    -e BACKEND_NAME="$BACKEND_NAME" \
    -e RESULTS_OUT="$RESULTS_OUT" \
    grafana/k6:0.54.0 "${K6_ARGS[@]}"
fi

python3 - <<PY
import json, sys
from pathlib import Path
p = Path("${RESULTS_OUT}")
assert p.is_file(), p
data = json.loads(p.read_text())
assert data.get("schema_version") == 1
assert "metrics" in data and "latency_ms" in data["metrics"]
print(f"OK: valid results skeleton at {p}")
PY
