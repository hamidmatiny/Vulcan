"""JSON Schema validation helpers for the Vulcan training-job contract."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from vulcan_training_contract.paths import SCHEMAS_DIR


@lru_cache(maxsize=16)
def load_json_schema(name: str) -> dict[str, Any]:
    """Load a schema file from ``schemas/`` by basename."""
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


def validate_training_job_spec(instance: dict[str, Any]) -> None:
    """Validate a TrainingJobSpec, including CPU-dev distributed constraints."""
    validate_instance(instance, "training-job-spec")
    if instance.get("cpu_dev_mode") is True:
        dist = instance["distributed"]
        if dist.get("dist_backend") != "gloo":
            raise ValidationError("cpu_dev_mode requires distributed.dist_backend=gloo")
        if int(dist.get("world_size", 0)) > 2:
            raise ValidationError("cpu_dev_mode caps world_size at 2 (ADR-009)")


def validate_training_job_result(instance: dict[str, Any]) -> None:
    """Validate a TrainingJobResult and basic metrics consistency."""
    validate_instance(instance, "training-job-result")
    metrics = instance["metrics"]
    if metrics["steps_completed"] < 0:
        raise ValidationError("steps_completed must be ≥ 0")
    if metrics["final_loss"] != metrics["final_loss"]:  # NaN
        raise ValidationError("final_loss must be a finite number")


def load_json_file(path: Path) -> Any:
    """Load a JSON document from disk."""
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)
