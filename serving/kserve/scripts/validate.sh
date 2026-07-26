#!/usr/bin/env bash
# Validate KServe Helm chart: helm template + kubeconform + conftest (ADR-002).
# Never applies manifests to a cluster.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/serving/kserve/helm"
POLICY="${ROOT}/serving/kserve/policy"
OUT_DIR="${ROOT}/serving/kserve/.render"
K8S_VERSION="${KUBECONFORM_K8S_VERSION:-1.29.0}"

mkdir -p "${OUT_DIR}"
rm -f "${OUT_DIR}"/*.yaml

echo "==> helm lint"
helm lint "${CHART}"

echo "==> helm template (default)"
helm template vulcan-kserve "${CHART}" \
  --namespace vulcan-serving \
  > "${OUT_DIR}/default.yaml"

echo "==> helm template (canary example)"
helm template vulcan-kserve "${CHART}" \
  --namespace vulcan-serving \
  -f "${CHART}/values.yaml" \
  -f "${CHART}/values-canary.yaml" \
  > "${OUT_DIR}/canary.yaml"

# Split multi-doc YAML for tools that prefer file-per-object (optional; kubeconform accepts multi-doc).
echo "==> kubeconform (core types; KServe CRDs ignore-missing-schemas)"
# InferenceService is a CRD — validate structure via conftest; kubeconform checks Namespace + syntax.
kubeconform \
  -kubernetes-version "${K8S_VERSION}" \
  -ignore-missing-schemas \
  -summary \
  "${OUT_DIR}/default.yaml" \
  "${OUT_DIR}/canary.yaml"

echo "==> conftest (OPA policies)"
conftest test \
  --policy "${POLICY}" \
  --namespace vulcan.kserve \
  "${OUT_DIR}/default.yaml" \
  "${OUT_DIR}/canary.yaml"

echo "==> conftest unit tests (rego)"
conftest verify --policy "${POLICY}"

# Sanity: canary render must include canaryTrafficPercent
grep -q 'canaryTrafficPercent: 10' "${OUT_DIR}/canary.yaml"
grep -q 'vulcan-triton:cpu-canary' "${OUT_DIR}/canary.yaml"
grep -q 'vulcan-vllm:cpu-canary' "${OUT_DIR}/canary.yaml"
# Default render must NOT enable canary
if grep -q 'canaryTrafficPercent:' "${OUT_DIR}/default.yaml"; then
  echo "default render unexpectedly contains canaryTrafficPercent" >&2
  exit 1
fi

echo "OK: KServe chart validation passed (no cluster apply)"
