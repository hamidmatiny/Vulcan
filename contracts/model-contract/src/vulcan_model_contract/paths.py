"""Filesystem anchors for the model-contract package."""

from __future__ import annotations

from pathlib import Path

# contracts/model-contract/ (package lives in src/vulcan_model_contract/)
CONTRACT_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = CONTRACT_ROOT / "schemas"
EXAMPLES_DIR = CONTRACT_ROOT / "examples"
OPENAPI_PATH = CONTRACT_ROOT / "openapi.yaml"
