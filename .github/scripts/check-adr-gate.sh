#!/usr/bin/env bash
# Fail CI when contracts/ or gpu-infra/ change without the required ADRs present.
# Mapping is intentional and narrow — extend as new ADRs land.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ADR_DIR="docs/adr"
ADR_CONTRACTS="001-unified-model-serving-contract.md"
ADR_GPU_INFRA="002-gpu-cost-safety-policy.md"

CHANGED_FILES=""
if [[ -n "${ADR_GATE_CHANGED_FILES:-}" ]]; then
  CHANGED_FILES="$ADR_GATE_CHANGED_FILES"
elif [[ -n "${GITHUB_BASE_REF:-}" ]]; then
  git fetch --no-tags --depth=1 origin "${GITHUB_BASE_REF}" 2>/dev/null || true
  if git rev-parse --verify "origin/${GITHUB_BASE_REF}" >/dev/null 2>&1; then
    CHANGED_FILES="$(git diff --name-only "origin/${GITHUB_BASE_REF}"...HEAD || true)"
  fi
fi

if [[ -z "${CHANGED_FILES}" ]]; then
  # First push / no base: treat tracked paths under contracts/ and gpu-infra/ as in-scope.
  CHANGED_FILES="$(git ls-files contracts gpu-infra || true)"
fi

touched_contracts=0
touched_gpu_infra=0

while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in
    contracts|contracts/*) touched_contracts=1 ;;
  esac
  case "$path" in
    gpu-infra|gpu-infra/*) touched_gpu_infra=1 ;;
  esac
done <<< "$CHANGED_FILES"

fail=0

check_adr() {
  local area="$1"
  local adr_file="$2"
  local full="${ADR_DIR}/${adr_file}"
  if [[ ! -f "$full" ]]; then
    echo "ADR gate FAIL: changes under ${area} require ${full}"
    fail=1
  else
    echo "ADR gate OK: ${area} → ${full}"
  fi
}

if [[ "$touched_contracts" -eq 1 ]]; then
  check_adr "contracts/" "$ADR_CONTRACTS"
fi

if [[ "$touched_gpu_infra" -eq 1 ]]; then
  check_adr "gpu-infra/" "$ADR_GPU_INFRA"
fi

if [[ "$touched_contracts" -eq 0 && "$touched_gpu_infra" -eq 0 ]]; then
  echo "ADR gate skip: no changes under contracts/ or gpu-infra/"
fi

if [[ "$touched_contracts" -eq 1 || "$touched_gpu_infra" -eq 1 ]]; then
  if [[ ! -f "${ADR_DIR}/index.md" ]]; then
    echo "ADR gate FAIL: ${ADR_DIR}/index.md is missing"
    fail=1
  fi
fi

exit "$fail"
