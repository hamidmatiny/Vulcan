"""JSON Schema validation helpers for the Vulcan model contract."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from vulcan_model_contract.paths import SCHEMAS_DIR


@lru_cache(maxsize=16)
def load_json_schema(name: str) -> dict[str, Any]:
    """Load a schema file from ``schemas/`` by basename (with or without ``.schema.json``)."""
    if name.endswith(".json"):
        path = SCHEMAS_DIR / name
    else:
        path = SCHEMAS_DIR / f"{name}.schema.json"
    if not path.is_file():
        raise FileNotFoundError(f"schema not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise TypeError(f"schema root must be an object: {path}")
    return data


def validate_instance(instance: Any, schema_name: str) -> None:
    """Validate ``instance`` against a named schema; raise ``ValidationError`` on failure."""
    schema = load_json_schema(schema_name)
    Draft202012Validator(schema).validate(instance)


def validate_resource_requirements(instance: dict[str, Any]) -> None:
    """Validate a resource-requirements manifest, including min≤max range checks."""
    validate_instance(instance, "resource-requirements")
    mem = instance["gpu_memory_mib"]
    if mem["min"] > mem["max"]:
        raise ValidationError("gpu_memory_mib.min must be ≤ gpu_memory_mib.max")
    cold = instance["cold_start_seconds"]
    if cold["min"] > cold["max"]:
        raise ValidationError("cold_start_seconds.min must be ≤ cold_start_seconds.max")


def load_json_file(path: Path) -> Any:
    """Load a JSON document from disk."""
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)
