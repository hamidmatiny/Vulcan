"""Schema / OpenAPI / example tests for the training-job contract."""

from __future__ import annotations

import json

import pytest
import yaml
from jsonschema.exceptions import ValidationError

from vulcan_training_contract.paths import EXAMPLES_DIR, OPENAPI_PATH, SCHEMAS_DIR
from vulcan_training_contract.validate import (
    validate_lora_fine_tune_result,
    validate_lora_fine_tune_spec,
    validate_training_job_result,
    validate_training_job_spec,
)


def test_schemas_present() -> None:
    assert (SCHEMAS_DIR / "training-job-spec.schema.json").is_file()
    assert (SCHEMAS_DIR / "training-job-result.schema.json").is_file()
    assert (SCHEMAS_DIR / "lora-fine-tune-spec.schema.json").is_file()
    assert (SCHEMAS_DIR / "lora-fine-tune-result.schema.json").is_file()


def test_openapi_paths() -> None:
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = doc["paths"]
    assert "/health" in paths
    assert "/metrics" in paths
    assert "/v1/training/spec" in paths
    assert "/v1/training/result" in paths
    assert "/v1/training/lora/spec" in paths
    assert "/v1/training/lora/result" in paths


def test_example_spec_valid() -> None:
    data = json.loads((EXAMPLES_DIR / "training-job-spec.cpu-dev.json").read_text(encoding="utf-8"))
    validate_training_job_spec(data)
    assert data["cpu_dev_mode"] is True
    assert data["model_id"] == "reference-tiny-llm"


def test_example_result_valid() -> None:
    data = json.loads(
        (EXAMPLES_DIR / "training-job-result.cpu-dev.json").read_text(encoding="utf-8")
    )
    validate_training_job_result(data)


def test_example_lora_spec_valid() -> None:
    data = json.loads(
        (EXAMPLES_DIR / "lora-fine-tune-spec.cpu-dev.json").read_text(encoding="utf-8")
    )
    validate_lora_fine_tune_spec(data)
    assert data["served_model_id"] == "reference-tiny-llm-lora-demo"
    assert data["lora"]["r"] in (4, 8)


def test_example_lora_result_valid() -> None:
    data = json.loads(
        (EXAMPLES_DIR / "lora-fine-tune-result.cpu-dev.json").read_text(encoding="utf-8")
    )
    validate_lora_fine_tune_result(data)
    assert data["verification"] == "structural_not_sha256"


def test_lora_result_rejects_zero_delta() -> None:
    data = json.loads(
        (EXAMPLES_DIR / "lora-fine-tune-result.cpu-dev.json").read_text(encoding="utf-8")
    )
    data["metrics"]["logits_delta_l1"] = 0.0
    with pytest.raises(ValidationError, match="logits_delta_l1"):
        validate_lora_fine_tune_result(data)


def test_cpu_dev_rejects_nccl() -> None:
    data = json.loads((EXAMPLES_DIR / "training-job-spec.cpu-dev.json").read_text(encoding="utf-8"))
    data["distributed"]["dist_backend"] = "nccl"
    with pytest.raises(ValidationError, match="gloo"):
        validate_training_job_spec(data)
