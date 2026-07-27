#!/usr/bin/env bash
# Trivy vuln scan (CRITICAL fail) + Syft SBOM for one local image.
set -euo pipefail

IMAGE="${1:?image name required e.g. vulcan-gateway:cpu}"
OUT_DIR="${2:-sboms}"
SAFE_NAME="$(echo "${IMAGE}" | tr '/:' '__')"
mkdir -p "${OUT_DIR}"

echo "==> Trivy ${IMAGE}"
trivy image --quiet --scanners vuln --severity CRITICAL --ignore-unfixed \
  --exit-code 1 "${IMAGE}"

echo "==> Syft SBOM ${IMAGE}"
syft "${IMAGE}" -o spdx-json="${OUT_DIR}/${SAFE_NAME}.spdx.json" -q
echo "OK ${IMAGE} → ${OUT_DIR}/${SAFE_NAME}.spdx.json"
