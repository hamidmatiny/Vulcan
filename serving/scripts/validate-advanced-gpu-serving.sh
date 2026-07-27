#!/usr/bin/env bash
# Validate phase-16 advanced GPU serving artifacts (no GPU, no engine build).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
if [[ -x contracts/model-contract/.venv/bin/python ]]; then
  PYTHON=contracts/model-contract/.venv/bin/python
elif [[ -x serving/common/.venv/bin/python ]]; then
  PYTHON=serving/common/.venv/bin/python
fi

echo "==> resource-requirements.json (gpu-variants) vs phase-0 schema"
"$PYTHON" - <<'PY'
from pathlib import Path
import json
import sys

root = Path(".")
sys.path.insert(0, str(root / "contracts" / "model-contract" / "src"))
from vulcan_model_contract.validate import validate_resource_requirements

paths = sorted((root / "serving" / "vllm" / "gpu-variants").glob("*/resource-requirements.json"))
assert paths, "no gpu-variants manifests found"
for path in paths:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_resource_requirements(data)
    assert data.get("supports_quantization") is True, path
    assert data.get("cpu_dev_mode") is False, path
    assert data["gpu_memory_mib"]["min"] > 0, path
    print("OK", path)
PY

echo "==> TensorRT-LLM config.pbtxt structural lint"
"$PYTHON" serving/triton/tensorrt-llm/scripts/validate_config_pbtxt.py

echo "==> ADR-007 present"
test -f docs/adr/007-advanced-gpu-serving-techniques-scope.md
test -f docs/runbooks/tensorrt-llm-build.md
echo "OK validate-advanced-gpu-serving"
