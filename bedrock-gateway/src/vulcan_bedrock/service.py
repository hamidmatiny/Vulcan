"""Vulcan Bedrock contract shim — LLM-branch surface for the phase-13 router."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

from vulcan_bedrock.client import DEFAULT_MODEL_ID, BedrockClient
from vulcan_bedrock.pricing import load_pricing_reference

try:
    from vulcan_model_contract.validate import validate_instance, validate_resource_requirements
except ImportError:  # pragma: no cover
    import sys

    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / "contracts" / "model-contract" / "src"))
    from vulcan_model_contract.validate import validate_instance, validate_resource_requirements

BACKEND_NAME = "bedrock"
BACKEND_VERSION = "0.11.0"
RESOURCES_PATH = Path(__file__).resolve().parents[2] / "resource-requirements.json"

app = FastAPI(title="Vulcan Bedrock contract shim", docs_url=None, redoc_url=None)

_registry = CollectorRegistry()
_infer_requests = Counter(
    "vulcan_infer_requests_total",
    "Total /v1/infer requests",
    ["backend", "status", "modality"],
    registry=_registry,
)
_infer_latency = Histogram(
    "vulcan_infer_latency_seconds",
    "Inference latency seconds",
    ["backend", "modality"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
    registry=_registry,
)
for _status, _modality in (
    ("ok", "llm"),
    ("error", "unknown"),
    ("error", "llm"),
    ("error", "vision"),
    ("unsupported", "vision"),
):
    _infer_requests.labels(BACKEND_NAME, _status, _modality)
_infer_latency.labels(BACKEND_NAME, "llm")

_client: BedrockClient | None = None


def _default_model_id() -> str:
    return os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)


def _region() -> str:
    return os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or "us-east-1"


def get_client() -> BedrockClient:
    global _client
    if _client is None:
        _client = BedrockClient(region=_region())
    return _client


def set_client(client: BedrockClient | None) -> None:
    """Test hook to inject a mocked BedrockClient."""
    global _client
    _client = client


def _load_resources() -> dict[str, Any]:
    data = json.loads(RESOURCES_PATH.read_text(encoding="utf-8"))
    validate_resource_requirements(data)
    return data


def _error(status: int, error: str, message: str, request_id: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": error, "message": message}
    if request_id is not None:
        body["request_id"] = request_id
    return JSONResponse(status_code=status, content=body)


@app.get("/health")
def health() -> JSONResponse:
    # Lightweight: no live Bedrock ping (would spend money / need real creds).
    payload = {
        "status": "ok",
        "backend": BACKEND_NAME,
        "model_id": _default_model_id(),
        "version": BACKEND_VERSION,
        # Contract mode enum is cpu|gpu; managed Bedrock has no local device — report cpu
        # for the mocked/dev path (cpu_dev_mode in resource-requirements).
        "mode": "cpu",
        "detail": (
            f"region={_region()};modalities=llm;vision=unsupported;"
            "runtime=bedrock-managed;readiness=config-only "
            "(InvokeModel not probed on /health)"
        ),
    }
    validate_instance(payload, "health")
    return JSONResponse(status_code=200, content=payload)


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(_registry).decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/resources")
def resources() -> dict[str, Any]:
    return _load_resources()


@app.get("/v1/pricing-reference")
def pricing_reference() -> dict[str, Any]:
    """Static cost/latency map for the phase-13 router (not live AWS Pricing)."""
    return load_pricing_reference()


@app.post("/v1/infer")
async def infer(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        _infer_requests.labels(BACKEND_NAME, "error", "unknown").inc()
        return _error(400, "invalid_json", "body must be JSON")

    if not isinstance(payload, dict):
        _infer_requests.labels(BACKEND_NAME, "error", "unknown").inc()
        return _error(400, "invalid_request", "body must be a JSON object")

    request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) else None
    try:
        validate_instance(payload, "infer-request")
    except Exception as exc:  # noqa: BLE001
        _infer_requests.labels(BACKEND_NAME, "error", str(payload.get("modality", "unknown"))).inc()
        return _error(400, "invalid_request", str(exc), request_id)

    modality = payload["modality"]
    model_id = payload["model_id"]

    if modality == "vision":
        _infer_requests.labels(BACKEND_NAME, "unsupported", "vision").inc()
        return _error(
            400,
            "unsupported_modality",
            "bedrock-gateway is LLM-only; vision is not implemented on this adapter "
            "(use bentoml, ray-serve, or triton for reference-tiny-vision)",
            request_id,
        )

    if modality != "llm":
        _infer_requests.labels(BACKEND_NAME, "error", "unknown").inc()
        return _error(400, "invalid_request", f"unsupported modality: {modality}", request_id)

    started = time.perf_counter()
    try:
        inp = payload["input"]
        output = get_client().infer_llm(
            model_id=model_id,
            messages=inp["messages"],
            max_tokens=int(inp.get("max_tokens") or 256),
            temperature=float(inp.get("temperature") or 0.0),
        )
    except Exception as exc:  # noqa: BLE001
        _infer_requests.labels(BACKEND_NAME, "error", "llm").inc()
        return _error(502, "infer_failed", str(exc), request_id)

    latency_ms = (time.perf_counter() - started) * 1000.0
    _infer_latency.labels(BACKEND_NAME, "llm").observe(latency_ms / 1000.0)
    _infer_requests.labels(BACKEND_NAME, "ok", "llm").inc()
    response = {
        "request_id": payload["request_id"],
        "modality": "llm",
        "model_id": model_id,
        "output": output,
        "latency_ms": latency_ms,
    }
    validate_instance(response, "infer-response")
    return JSONResponse(status_code=200, content=response)


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    # Vulcan host ports 9000–9099; 9006 reserved for this optional local shim (no compose).
    port = int(os.environ.get("PORT", "9006"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
