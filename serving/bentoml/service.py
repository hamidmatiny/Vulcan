"""Vulcan BentoML adapter — phase-0 model contract over GPT-2 + ResNet-18."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import bentoml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from models_runtime import (
    LLM_MODEL_ID,
    VISION_MODEL_ID,
    LlmBundle,
    VisionBundle,
    load_llm,
    load_vision,
)

try:
    from vulcan_model_contract.validate import validate_instance, validate_resource_requirements
except ImportError:  # pragma: no cover — docker image may put contracts on PYTHONPATH
    import sys

    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT / "contracts" / "model-contract" / "src"))
    from vulcan_model_contract.validate import validate_instance, validate_resource_requirements

BACKEND_NAME = "bentoml"
BACKEND_VERSION = "0.2.0"
RESOURCES_PATH = Path(__file__).resolve().parent / "resource-requirements.json"

INFER_REQUESTS = Counter(
    "vulcan_infer_requests_total",
    "Total /v1/infer requests",
    ["backend", "status", "modality"],
)
INFER_LATENCY = Histogram(
    "vulcan_infer_latency_seconds",
    "Inference latency seconds",
    ["backend", "modality"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

app = FastAPI(title="Vulcan BentoML contract surface", docs_url=None, redoc_url=None)
try:
    from vulcan_serving_common.otel import instrument_fastapi
except ImportError:  # pragma: no cover — docker copies otel_setup.py
    from otel_setup import instrument_fastapi  # type: ignore

instrument_fastapi(app, BACKEND_NAME)
_state_lock = threading.Lock()
_ready = False
_llm: LlmBundle | None = None
_vision: VisionBundle | None = None


def _runtime_mode() -> str:
    mode = os.environ.get("VULCAN_RUNTIME_MODE", "cpu").lower()
    return "gpu" if mode == "gpu" else "cpu"


def _load_resources() -> dict[str, Any]:
    data = json.loads(RESOURCES_PATH.read_text(encoding="utf-8"))
    validate_resource_requirements(data)
    return data


def _error(status: int, error: str, message: str, request_id: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": error, "message": message}
    if request_id is not None:
        body["request_id"] = request_id
    return JSONResponse(status_code=status, content=body)


@bentoml.service(
    name="vulcan-bentoml",
    traffic={"timeout": 120},
    resources={"cpu": "2", "memory": "4Gi"},
    workers=1,
)
@bentoml.asgi_app(app)
class VulcanService:
    """BentoML Service hosting both phase-1 reference models behind the Vulcan contract."""

    def __init__(self) -> None:
        global _ready, _llm, _vision
        with _state_lock:
            _ready = False
        # Eager load so /health is accurate after worker start.
        _llm = load_llm()
        _vision = load_vision()
        with _state_lock:
            _ready = True

    @app.get("/health")
    def health(self) -> JSONResponse:
        with _state_lock:
            ready = _ready
        status = "ok" if ready else "starting"
        payload = {
            "status": status,
            "backend": BACKEND_NAME,
            "model_id": LLM_MODEL_ID,
            "version": BACKEND_VERSION,
            "mode": _runtime_mode(),
            "detail": f"models={LLM_MODEL_ID},{VISION_MODEL_ID}",
        }
        validate_instance(payload, "health")
        return JSONResponse(status_code=200 if ready else 503, content=payload)

    @app.get("/metrics")
    def metrics(self) -> PlainTextResponse:
        return PlainTextResponse(
            generate_latest().decode("utf-8"),
            media_type=CONTENT_TYPE_LATEST,
        )

    @app.get("/v1/resources")
    def resources(self) -> dict[str, Any]:
        return _load_resources()

    @app.post("/v1/infer")
    async def infer(self, request: Request) -> JSONResponse:
        with _state_lock:
            ready = _ready
            llm = _llm
            vision = _vision
        if not ready or llm is None or vision is None:
            return _error(503, "not_ready", "backend starting")

        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            INFER_REQUESTS.labels(BACKEND_NAME, "error", "unknown").inc()
            return _error(400, "invalid_json", "body must be JSON")

        if not isinstance(payload, dict):
            INFER_REQUESTS.labels(BACKEND_NAME, "error", "unknown").inc()
            return _error(400, "invalid_request", "body must be a JSON object")

        request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) else None
        try:
            validate_instance(payload, "infer-request")
        except Exception as exc:  # noqa: BLE001
            INFER_REQUESTS.labels(BACKEND_NAME, "error", str(payload.get("modality", "unknown"))).inc()
            return _error(400, "invalid_request", str(exc), request_id)

        modality = payload["modality"]
        model_id = payload["model_id"]
        started = time.perf_counter()
        try:
            if modality == "llm":
                if model_id != LLM_MODEL_ID:
                    raise ValueError(f"unknown llm model_id: {model_id}")
                inp = payload["input"]
                output = llm.generate(
                    messages=inp["messages"],
                    max_tokens=int(inp.get("max_tokens") or 16),
                    temperature=float(inp.get("temperature") or 0.0),
                )
            elif modality == "vision":
                if model_id != VISION_MODEL_ID:
                    raise ValueError(f"unknown vision model_id: {model_id}")
                inp = payload["input"]
                output = vision.classify(
                    images=inp["images"],
                    prompt=inp.get("prompt"),
                )
            else:  # pragma: no cover — schema rejects others
                raise ValueError(f"unsupported modality: {modality}")
        except Exception as exc:  # noqa: BLE001
            INFER_REQUESTS.labels(BACKEND_NAME, "error", modality).inc()
            return _error(400, "infer_failed", str(exc), request_id)

        latency_ms = (time.perf_counter() - started) * 1000.0
        INFER_LATENCY.labels(BACKEND_NAME, modality).observe(latency_ms / 1000.0)
        INFER_REQUESTS.labels(BACKEND_NAME, "ok", modality).inc()
        response = {
            "request_id": payload["request_id"],
            "modality": modality,
            "model_id": model_id,
            "output": output,
            "latency_ms": latency_ms,
        }
        validate_instance(response, "infer-response")
        return JSONResponse(status_code=200, content=response)
