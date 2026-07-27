"""Filesystem anchors for the training-job contract package."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
CONTRACT_ROOT = PACKAGE_ROOT.parents[1]
SCHEMAS_DIR = CONTRACT_ROOT / "schemas"
EXAMPLES_DIR = CONTRACT_ROOT / "examples"
OPENAPI_PATH = CONTRACT_ROOT / "openapi.yaml"
