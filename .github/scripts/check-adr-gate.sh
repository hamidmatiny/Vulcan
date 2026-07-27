#!/usr/bin/env bash
# Fail CI when contracts/, gpu-infra/, autoscaling/, gateway/, advanced GPU
# serving, cost/GPU-metrics, or training paths change without required ADRs.
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
ADR_ADVANCED_GPU="007-advanced-gpu-serving-techniques-scope.md"
ADR_COST_TOKEN="008-self-hosted-cost-per-token-assumptions.md"
ADR_TRAINING_GPU_COST="009-gpu-cost-safety-extends-to-training.md"
ADR_TRAINING_CONTRACT="010-unified-training-job-contract.md"
ADR_LORA_PEFT="011-lora-peft-adapter-serving-integration.md"
ADR_DVC="012-data-versioning-with-dvc.md"
ADR_TRACKING="013-pluggable-experiment-tracking.md"

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
  CHANGED_FILES="$(git ls-files contracts gpu-infra autoscaling gateway serving/vllm/gpu-variants serving/triton/tensorrt-llm observability/gpu-metrics observability/cost-exporter/gpu-hour-assumptions.json training dvc.yaml dvc.lock .dvc models/scripts docs/adr/012-data-versioning-with-dvc.md docs/runbooks/dvc-remote.md docs/adr/013-pluggable-experiment-tracking.md || true)"
fi

touched_contracts=0
touched_gpu_infra=0
touched_mig_or_operator=0
touched_kueue=0
touched_autoscaling=0
touched_gateway=0
touched_advanced_gpu=0
touched_cost_token=0
touched_training=0
touched_lora=0
touched_dvc=0
touched_tracking=0

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
  case "$path" in
    serving/vllm/gpu-variants|serving/vllm/gpu-variants/*|serving/triton/tensorrt-llm|serving/triton/tensorrt-llm/*)
      touched_advanced_gpu=1
      ;;
  esac
  case "$path" in
    observability/gpu-metrics|observability/gpu-metrics/*|observability/cost-exporter/gpu-hour-assumptions.json)
      touched_cost_token=1
      ;;
  esac
  case "$path" in
    training|training/*|contracts/training-job-contract|contracts/training-job-contract/*)
      touched_training=1
      ;;
  esac
  case "$path" in
    training/fsdp-ddp/lora|training/fsdp-ddp/lora/*|contracts/training-job-contract/schemas/lora-*|contracts/training-job-contract/examples/lora-*|serving/bentoml/resource-requirements-lora-demo.json|serving/bentoml/tests/test_lora_logits_delta.py|docs/adr/011-lora-peft-adapter-serving-integration.md)
      touched_lora=1
      ;;
  esac
  case "$path" in
    dvc.yaml|dvc.lock|.dvc|.dvc/*|models/scripts/*dvc*|docs/adr/012-data-versioning-with-dvc.md|docs/runbooks/dvc-remote.md)
      touched_dvc=1
      ;;
  esac
  case "$path" in
    training/common/tracking.py|training/common/tracking*|training/common/verify_tracking.py|training/common/requirements-tracking.txt|training/common/tests/test_tracking.py|training/common/Dockerfile.mlflow|docs/adr/013-pluggable-experiment-tracking.md)
      touched_tracking=1
      ;;
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

if [[ "$touched_advanced_gpu" -eq 1 ]]; then
  check_adr "serving/vllm/gpu-variants|serving/triton/tensorrt-llm/" "$ADR_ADVANCED_GPU"
fi

if [[ "$touched_cost_token" -eq 1 ]]; then
  check_adr "observability/gpu-metrics|gpu-hour-assumptions.json" "$ADR_COST_TOKEN"
fi

if [[ "$touched_training" -eq 1 ]]; then
  check_adr "training/|contracts/training-job-contract/" "$ADR_TRAINING_GPU_COST"
  check_adr "training/|contracts/training-job-contract/" "$ADR_TRAINING_CONTRACT"
fi

if [[ "$touched_lora" -eq 1 ]]; then
  check_adr "training/fsdp-ddp/lora/|lora schemas|bentoml lora" "$ADR_LORA_PEFT"
fi

if [[ "$touched_dvc" -eq 1 ]]; then
  check_adr "dvc.yaml|.dvc/|models/scripts/*dvc*" "$ADR_DVC"
fi

if [[ "$touched_tracking" -eq 1 ]]; then
  check_adr "training/common/tracking*|verify_tracking" "$ADR_TRACKING"
fi

if [[ "$touched_contracts" -eq 0 && "$touched_gpu_infra" -eq 0 && "$touched_autoscaling" -eq 0 && "$touched_gateway" -eq 0 && "$touched_advanced_gpu" -eq 0 && "$touched_cost_token" -eq 0 && "$touched_training" -eq 0 && "$touched_lora" -eq 0 && "$touched_dvc" -eq 0 && "$touched_tracking" -eq 0 ]]; then
  echo "ADR gate skip: no changes under gated paths"
fi

if [[ "$touched_contracts" -eq 1 || "$touched_gpu_infra" -eq 1 || "$touched_autoscaling" -eq 1 || "$touched_gateway" -eq 1 || "$touched_advanced_gpu" -eq 1 || "$touched_cost_token" -eq 1 || "$touched_training" -eq 1 || "$touched_lora" -eq 1 || "$touched_dvc" -eq 1 || "$touched_tracking" -eq 1 ]]; then
  if [[ ! -f "${ADR_DIR}/index.md" ]]; then
    echo "ADR gate FAIL: ${ADR_DIR}/index.md is missing"
    fail=1
  fi
fi

exit "$fail"
