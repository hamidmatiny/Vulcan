#!/usr/bin/env bash
# Fail CI when contracts/, gpu-infra/, autoscaling/, or gateway/ change without required ADRs.
# Mapping is intentional and narrow — extend as new ADRs land.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ADR_DIR="docs/adr"
ADR_CONTRACTS="001-unified-model-serving-contract.md"
ADR_GPU_COST="002-gpu-cost-safety-policy.md"
ADR_MIG="003-mig-partitioning-strategy.md"
ADR_KUEUE="004-multi-tenant-gpu-scheduling-with-kueue.md"
ADR_SPOT="005-spot-gpu-strategy.md"
ADR_ROUTING="006-routing-policy.md"

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
  CHANGED_FILES="$(git ls-files contracts gpu-infra autoscaling gateway || true)"
fi

touched_contracts=0
touched_gpu_infra=0
touched_mig_or_operator=0
touched_kueue=0
touched_autoscaling=0
touched_gateway=0

while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in
    contracts|contracts/*) touched_contracts=1 ;;
  esac
  case "$path" in
    gpu-infra|gpu-infra/*) touched_gpu_infra=1 ;;
  esac
  case "$path" in
    gpu-infra/mig|gpu-infra/mig/*|gpu-infra/gpu-operator|gpu-infra/gpu-operator/*)
      touched_mig_or_operator=1
      ;;
  esac
  case "$path" in
    gpu-infra/kueue|gpu-infra/kueue/*) touched_kueue=1 ;;
  esac
  case "$path" in
    autoscaling|autoscaling/*) touched_autoscaling=1 ;;
  esac
  case "$path" in
    gateway|gateway/*) touched_gateway=1 ;;
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
  check_adr "gpu-infra/" "$ADR_GPU_COST"
fi

if [[ "$touched_mig_or_operator" -eq 1 ]]; then
  check_adr "gpu-infra/mig|gpu-operator/" "$ADR_MIG"
fi

if [[ "$touched_kueue" -eq 1 ]]; then
  check_adr "gpu-infra/kueue/" "$ADR_KUEUE"
fi

if [[ "$touched_autoscaling" -eq 1 ]]; then
  check_adr "autoscaling/" "$ADR_SPOT"
fi

if [[ "$touched_gateway" -eq 1 ]]; then
  check_adr "gateway/" "$ADR_ROUTING"
fi

if [[ "$touched_contracts" -eq 0 && "$touched_gpu_infra" -eq 0 && "$touched_autoscaling" -eq 0 && "$touched_gateway" -eq 0 ]]; then
  echo "ADR gate skip: no changes under contracts/, gpu-infra/, autoscaling/, or gateway/"
fi

if [[ "$touched_contracts" -eq 1 || "$touched_gpu_infra" -eq 1 || "$touched_autoscaling" -eq 1 || "$touched_gateway" -eq 1 ]]; then
  if [[ ! -f "${ADR_DIR}/index.md" ]]; then
    echo "ADR gate FAIL: ${ADR_DIR}/index.md is missing"
    fail=1
  fi
fi

exit "$fail"
