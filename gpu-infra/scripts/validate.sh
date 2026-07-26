#!/usr/bin/env bash
# Validate GPU Operator overlays, MIG profiles, and Terraform (ADR-002: no apply).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${ROOT}/gpu-infra/.render"
CHART="${ROOT}/gpu-infra/gpu-operator/chart"
POLICY="${ROOT}/gpu-infra/policy"
TF_DIR="${ROOT}/infra/terraform/environments/gpu-eks"
K8S_VERSION="${KUBECONFORM_K8S_VERSION:-1.29.0}"

mkdir -p "${OUT}"
rm -f "${OUT}"/*.yaml "${OUT}"/*.json

echo "==> helm lint (vulcan GPU Operator overlays)"
helm lint "${CHART}"

echo "==> helm template (device plugin + MIG ConfigMaps)"
helm template vulcan-gpu-overlays "${CHART}" > "${OUT}/overlays.yaml"

echo "==> kubeconform"
kubeconform \
  -kubernetes-version "${K8S_VERSION}" \
  -summary \
  "${OUT}/overlays.yaml" \
  "${ROOT}/gpu-infra/mig/profiles/combined-configmap.yaml"

echo "==> conftest (rendered overlays + MIG profiles)"
conftest test \
  --policy "${POLICY}" \
  --namespace vulcan.gpu_infra \
  "${OUT}/overlays.yaml" \
  "${ROOT}/gpu-infra/mig/profiles/combined-configmap.yaml"

echo "==> conftest (GPU Operator values separation)"
# Strip comments for YAML parse; conftest accepts YAML files as input.
conftest test \
  --policy "${POLICY}" \
  --namespace vulcan.gpu_operator_values \
  "${ROOT}/gpu-infra/gpu-operator/values-eks.yaml"

echo "==> conftest unit tests"
conftest verify --policy "${POLICY}"

echo "==> terraform init/validate/plan (local backend, mock vars, no apply)"
if ! command -v terraform >/dev/null 2>&1; then
  echo "terraform not found on PATH" >&2
  exit 1
fi
(
  cd "${TF_DIR}"
  rm -rf .terraform
  # Documented local backend (versions.tf); CI never applies (ADR-002).
  terraform init -input=false -reconfigure
  terraform validate
  terraform plan \
    -var-file=ci.tfvars \
    -refresh=false \
    -input=false \
    -out="${OUT}/gpu-eks.tfplan"
  terraform show -json "${OUT}/gpu-eks.tfplan" > "${OUT}/gpu-eks.tfplan.json"
  # Sanity: plan must mention GPU node groups / taints
  grep -q 'gpu-inference\|gpu-mig' "${OUT}/gpu-eks.tfplan.json"
)

# Sanity: values files keep driver/plugin separation documented
grep -q 'driver:' "${ROOT}/gpu-infra/gpu-operator/values-eks.yaml"
grep -q 'devicePlugin:' "${ROOT}/gpu-infra/gpu-operator/values-eks.yaml"
grep -q 'many-small-inference' "${ROOT}/gpu-infra/mig/values-mig.yaml"
grep -q 'training-large-batch' "${ROOT}/gpu-infra/mig/values-mig.yaml"

echo "OK: gpu-infra validation passed (no cluster/cloud apply)"
