"""Contract-conformance suite — point any backend at VULCAN_BACKEND_URL."""

from __future__ import annotations

import re

import pytest
from vulcan_model_contract.validate import validate_instance, validate_resource_requirements

from vulcan_serving_common.client import VulcanClient, VulcanClientError

# 1x1 PNG
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

_PROM_LINE = re.compile(
    r"^(?:# (?:HELP|TYPE) |[a-zA-Z_:][a-zA-Z0-9_:]*(?:\{[^}]*\})? (?:[0-9eE+.\-]+|NaN|Inf|\+Inf))"
)


def test_health_ok_schema(client: VulcanClient) -> None:
    health = client.health()
    validate_instance(health, "health")
    assert health["status"] == "ok"
    assert health["mode"] == "cpu"


def test_resources_schema(client: VulcanClient) -> None:
    resources = client.resources()
    validate_resource_requirements(resources)
    assert resources["cpu_dev_mode"] is True


def test_metrics_prometheus_format(client: VulcanClient) -> None:
    body = client.metrics()
    assert body.strip(), "metrics body must be non-empty"
    lines = [ln for ln in body.splitlines() if ln.strip()]
    assert any(ln.startswith("# HELP") for ln in lines)
    assert any(ln.startswith("# TYPE") for ln in lines)
    samples = [ln for ln in lines if not ln.startswith("#")]
    assert samples, "expected at least one metric sample"
    for ln in samples:
        assert _PROM_LINE.match(ln), f"invalid prometheus line: {ln}"
    assert "vulcan_infer" in body or "http_" in body or "_total" in body


def test_infer_llm_schema(client: VulcanClient) -> None:
    resp = client.infer_llm(
        model_id="reference-tiny-llm",
        messages=[{"role": "user", "content": "hello"}],
        request_id="conf-llm-1",
    )
    validate_instance(resp, "infer-response")
    assert resp["modality"] == "llm"
    assert resp["request_id"] == "conf-llm-1"
    assert isinstance(resp["output"]["text"], str)


def test_infer_vision_schema(client: VulcanClient) -> None:
    resp = client.infer_vision(
        model_id="reference-tiny-vision",
        images=[{"media_type": "image/png", "data_base64": _TINY_PNG_B64}],
        prompt="what is this?",
        request_id="conf-vision-1",
    )
    validate_instance(resp, "infer-response")
    assert resp["modality"] == "vision"
    assert resp["request_id"] == "conf-vision-1"


def test_infer_invalid_modality_400(client: VulcanClient) -> None:
    with pytest.raises(VulcanClientError) as exc:
        client.infer(
            {
                "request_id": "bad-1",
                "modality": "audio",
                "model_id": "reference-tiny-llm",
                "input": {"messages": [{"role": "user", "content": "x"}]},
            }
        )
    assert exc.value.status_code == 400
    assert isinstance(exc.value.body, dict)
    assert "error" in exc.value.body
    assert "message" in exc.value.body


def test_infer_missing_fields_400(client: VulcanClient) -> None:
    with pytest.raises(VulcanClientError) as exc:
        client.infer({"modality": "llm"})
    assert exc.value.status_code == 400
