#!/usr/bin/env bash
# Validate Karpenter GPU NodePools (ADR-002: no apply).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/autoscaling/karpenter/chart"
POLICY="${ROOT}/autoscaling/karpenter/policy"
OUT="${ROOT}/autoscaling/karpenter/.render"
K8S_VERSION="${KUBECONFORM_K8S_VERSION:-1.29.0}"

mkdir -p "${OUT}"
rm -f "${OUT}"/*.yaml

echo "==> helm lint + template (Karpenter)"
helm lint "${CHART}"
helm template vulcan-karpenter-gpu "${CHART}" > "${OUT}/karpenter.yaml"

echo "==> kubeconform"
kubeconform \
  -kubernetes-version "${K8S_VERSION}" \
  -ignore-missing-schemas \
  -summary \
  "${OUT}/karpenter.yaml"

echo "==> structural checks"
grep -q 'kind: EC2NodeClass' "${OUT}/karpenter.yaml"
grep -q 'kind: NodePool' "${OUT}/karpenter.yaml"
grep -q 'vulcan-gpu-mig-small' "${OUT}/karpenter.yaml"
grep -q 'vulcan-gpu-mig-large' "${OUT}/karpenter.yaml"
grep -q 'many-small-inference' "${OUT}/karpenter.yaml"
grep -q 'training-large-batch' "${OUT}/karpenter.yaml"
grep -q 'consolidationPolicy' "${OUT}/karpenter.yaml"
grep -q 'budgets:' "${OUT}/karpenter.yaml"

echo "==> conftest"
conftest test --policy "${POLICY}" --namespace vulcan.karpenter "${OUT}/karpenter.yaml"
conftest verify --policy "${POLICY}"

echo "OK: Karpenter manifests validated (no cluster apply)"
