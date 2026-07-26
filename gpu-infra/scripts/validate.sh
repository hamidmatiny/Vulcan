#!/usr/bin/env bash
# Validate GPU Operator overlays, MIG, Kueue, and Terraform (ADR-002: no apply).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${ROOT}/gpu-infra/.render"
CHART="${ROOT}/gpu-infra/gpu-operator/chart"
KUEUE_CHART="${ROOT}/gpu-infra/kueue/chart"
POLICY="${ROOT}/gpu-infra/policy"
KUEUE_POLICY="${ROOT}/gpu-infra/kueue/policy"
TF_DIR="${ROOT}/infra/terraform/environments/gpu-eks"
K8S_VERSION="${KUBECONFORM_K8S_VERSION:-1.29.0}"

mkdir -p "${OUT}"
rm -f "${OUT}"/*.yaml "${OUT}"/*.json

echo "==> helm lint (vulcan GPU Operator overlays)"
helm lint "${CHART}"

echo "==> helm template (device plugin + MIG ConfigMaps)"
helm template vulcan-gpu-overlays "${CHART}" > "${OUT}/overlays.yaml"

echo "==> helm lint + template (Kueue queues / flavors / priorities)"
helm lint "${KUEUE_CHART}"
helm template vulcan-kueue "${KUEUE_CHART}" > "${OUT}/kueue.yaml"

echo "==> kubeconform (core types; CRDs ignore-missing-schemas)"
kubeconform \
  -kubernetes-version "${K8S_VERSION}" \
  -ignore-missing-schemas \
  -summary \
  "${OUT}/overlays.yaml" \
  "${ROOT}/gpu-infra/mig/profiles/combined-configmap.yaml" \
  "${OUT}/kueue.yaml" \
  "${ROOT}/gpu-infra/kueue/examples/workload-kserve-inferenceservice.yaml" \
  "${ROOT}/gpu-infra/kueue/examples/workload-training-job.yaml"

# kubectl dry-run equivalent without a cluster: client-side validation via kubeconform above
# plus structural grep sanity for required Kueue kinds.
echo "==> kubectl dry-run equivalent (structural kind checks)"
for kind in ResourceFlavor ClusterQueue LocalQueue WorkloadPriorityClass; do
  grep -q "kind: ${kind}" "${OUT}/kueue.yaml"
done
grep -q 'kind: Workload' "${ROOT}/gpu-infra/kueue/examples/workload-kserve-inferenceservice.yaml"
grep -q 'kind: Workload' "${ROOT}/gpu-infra/kueue/examples/workload-training-job.yaml"
grep -q 'kind: InferenceService' "${ROOT}/gpu-infra/kueue/examples/workload-kserve-inferenceservice.yaml"
grep -q 'kind: Job' "${ROOT}/gpu-infra/kueue/examples/workload-training-job.yaml"

echo "==> conftest (rendered overlays + MIG profiles)"
conftest test \
  --policy "${POLICY}" \
  --namespace vulcan.gpu_infra \
  "${OUT}/overlays.yaml" \
  "${ROOT}/gpu-infra/mig/profiles/combined-configmap.yaml"

echo "==> conftest (GPU Operator values separation)"
conftest test \
  --policy "${POLICY}" \
  --namespace vulcan.gpu_operator_values \
  "${ROOT}/gpu-infra/gpu-operator/values-eks.yaml"

echo "==> conftest (Kueue queues + example Workloads)"
conftest test \
  --policy "${KUEUE_POLICY}" \
  --namespace vulcan.kueue \
  "${OUT}/kueue.yaml" \
  "${ROOT}/gpu-infra/kueue/examples/workload-kserve-inferenceservice.yaml" \
  "${ROOT}/gpu-infra/kueue/examples/workload-training-job.yaml"

echo "==> conftest unit tests"
conftest verify --policy "${POLICY}"
conftest verify --policy "${KUEUE_POLICY}"

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
grep -q 'cq-inference' "${OUT}/kueue.yaml"
grep -q 'cq-training' "${OUT}/kueue.yaml"
grep -q 'vulcan-gpu-cohort' "${OUT}/kueue.yaml"

echo "OK: gpu-infra validation passed (no cluster/cloud apply)"
