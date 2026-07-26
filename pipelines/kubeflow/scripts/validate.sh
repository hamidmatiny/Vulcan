#!/usr/bin/env bash
# Compile KFP pipeline + validate PyTorchJob / InferenceService (ADR-002: no apply).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PIPE="${ROOT}/pipelines/kubeflow/pipelines"
TRAIN="${ROOT}/pipelines/kubeflow/training-operator"
OUT="${ROOT}/pipelines/kubeflow/.render"
K8S_VERSION="${KUBECONFORM_K8S_VERSION:-1.29.0}"
VENV="${PIPE}/.venv"
PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON=python3.12
  else
    PYTHON=python3
  fi
fi

mkdir -p "${OUT}"
rm -f "${OUT}"/*.yaml "${OUT}"/*.json

echo "==> compile KFP pipeline (python=${PYTHON})"
# Recreate venv if missing or wrong interpreter major (avoid 3.14 + kfp quirks).
if [[ ! -x "${VENV}/bin/vulcan-kfp-compile" ]]; then
  rm -rf "${VENV}"
  "${PYTHON}" -m venv "${VENV}"
  "${VENV}/bin/pip" install -U pip
  "${VENV}/bin/pip" install -e "${PIPE}[dev]"
fi
"${VENV}/bin/vulcan-kfp-compile" -o "${PIPE}/compiled/vulcan-reference-tiny-llm.yaml"
cp "${PIPE}/compiled/vulcan-reference-tiny-llm.yaml" "${OUT}/pipeline.yaml"
grep -q 'vulcan-reference-tiny-llm' "${OUT}/pipeline.yaml"
grep -qi 'train' "${OUT}/pipeline.yaml"

echo "==> kubeconform (PyTorchJob + InferenceService; CRDs ignore-missing-schemas)"
kubeconform \
  -kubernetes-version "${K8S_VERSION}" \
  -ignore-missing-schemas \
  -summary \
  "${TRAIN}/manifests/pytorchjob-reference-tiny-llm.yaml" \
  "${PIPE}/handoff/inferenceservice-reference-tiny-llm.yaml"

echo "==> structural composition checks"
grep -q 'lq-training' "${TRAIN}/manifests/pytorchjob-reference-tiny-llm.yaml"
grep -q 'vulcan.dev/gpu-pool: mig-large' "${TRAIN}/manifests/pytorchjob-reference-tiny-llm.yaml"
grep -q 'vulcan-checkpoint-finetune' "${TRAIN}/manifests/pytorchjob-reference-tiny-llm.yaml"
grep -q 'vulcan.dev/backend: vllm' "${PIPE}/handoff/inferenceservice-reference-tiny-llm.yaml"
grep -q 'serving.kserve.io/deploymentMode: RawDeployment' "${PIPE}/handoff/inferenceservice-reference-tiny-llm.yaml"

echo "==> conftest"
conftest test --policy "${TRAIN}/policy" --namespace vulcan.kubeflow.training \
  "${TRAIN}/manifests/pytorchjob-reference-tiny-llm.yaml"
conftest verify --policy "${TRAIN}/policy"
conftest test --policy "${PIPE}/policy" --namespace vulcan.kubeflow.handoff \
  "${PIPE}/handoff/inferenceservice-reference-tiny-llm.yaml"
conftest verify --policy "${PIPE}/policy"

echo "==> unit tests (eval/handoff/compile)"
cd "${PIPE}"
"${VENV}/bin/pytest" -q tests \
  --cov=vulcan_kfp --cov-report=term-missing --cov-fail-under="${COVERAGE_MIN:-65}"
cd "${ROOT}"

echo "OK: Kubeflow pipeline compiled + manifests validated (no cluster apply)"
