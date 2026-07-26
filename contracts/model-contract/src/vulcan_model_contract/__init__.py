"""Vulcan model-serving contract helpers (schema loading + validation)."""

from __future__ import annotations

from vulcan_model_contract.paths import CONTRACT_ROOT, OPENAPI_PATH, SCHEMAS_DIR
from vulcan_model_contract.validate import (
    load_json_schema,
    validate_instance,
    validate_resource_requirements,
)

__all__ = [
    "CONTRACT_ROOT",
    "OPENAPI_PATH",
    "SCHEMAS_DIR",
    "load_json_schema",
    "validate_instance",
    "validate_resource_requirements",
]

__version__ = "0.1.0"
