"""Contract schema and example validation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema.exceptions import ValidationError

from vulcan_model_contract.paths import EXAMPLES_DIR, OPENAPI_PATH, SCHEMAS_DIR
from vulcan_model_contract.validate import (
    load_json_file,
    load_json_schema,
    validate_instance,
    validate_resource_requirements,
)

LLM_REQUEST = {
    "request_id": "req-1",
    "modality": "llm",
    "model_id": "reference-tiny-llm",
    "input": {
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 16,
        "temperature": 0.0,
    },
}

VISION_REQUEST = {
    "request_id": "req-2",
    "modality": "vision",
    "model_id": "reference-tiny-vision",
    "input": {
        "images": [
            {
                "media_type": "image/png",
                "data_base64": "aGVsbG8=",
            }
        ],
        "prompt": "describe",
    },
}


def test_schemas_dir_has_expected_files() -> None:
    expected = {
        "health.schema.json",
        "infer-request.schema.json",
        "infer-response.schema.json",
        "resource-requirements.schema.json",
    }
    present = {p.name for p in SCHEMAS_DIR.glob("*.schema.json")}
    assert expected <= present


def test_openapi_parses_and_exposes_required_paths() -> None:
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert doc["openapi"].startswith("3.")
    paths = doc["paths"]
    for required in ("/health", "/metrics", "/v1/infer", "/v1/resources"):
        assert required in paths


def test_cpu_dev_example_validates() -> None:
    example = load_json_file(EXAMPLES_DIR / "resource-requirements.cpu-dev.json")
    validate_resource_requirements(example)
    assert example["cpu_dev_mode"] is True
    assert example["gpu_memory_mib"]["min"] == 0


def test_infer_request_llm_and_vision() -> None:
    validate_instance(LLM_REQUEST, "infer-request")
    validate_instance(VISION_REQUEST, "infer-request")


def test_infer_request_rejects_unknown_modality() -> None:
    bad = {**LLM_REQUEST, "modality": "audio"}
    with pytest.raises(ValidationError):
        validate_instance(bad, "infer-request")


def test_infer_response_llm() -> None:
    response = {
        "request_id": "req-1",
        "modality": "llm",
        "model_id": "reference-tiny-llm",
        "output": {"text": "Hello", "finish_reason": "stop"},
        "latency_ms": 1.2,
    }
    validate_instance(response, "infer-response")


def test_health_schema() -> None:
    validate_instance(
        {
            "status": "ok",
            "backend": "vllm",
            "model_id": "reference-tiny-llm",
            "version": "0.1.0",
            "mode": "cpu",
        },
        "health",
    )


def test_resource_requirements_range_guards() -> None:
    base = json.loads(
        Path(EXAMPLES_DIR / "resource-requirements.cpu-dev.json").read_text(encoding="utf-8")
    )
    bad_mem = {**base, "gpu_memory_mib": {"min": 10, "max": 1}}
    with pytest.raises(ValidationError, match="gpu_memory_mib"):
        validate_resource_requirements(bad_mem)

    bad_cold = {**base, "cold_start_seconds": {"min": 9, "max": 1}}
    with pytest.raises(ValidationError, match="cold_start_seconds"):
        validate_resource_requirements(bad_cold)


def test_load_json_schema_missing() -> None:
    with pytest.raises(FileNotFoundError):
        load_json_schema("does-not-exist")
