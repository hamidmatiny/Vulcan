"""Vulcan Ray Serve adapter — phase-0 model contract over GPT-2 + ResNet-18."""

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
from ray import serve

from models_runtime import (
    LLM_MODEL_ID,
    VISION_MODEL_ID,
    load_llm,
    load_vision,
)

try:
    from vulcan_model_contract.validate import validate_instance, validate_resource_requirements
except ImportError:  # pragma: no cover
    import sys

    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT / "contracts" / "model-contract" / "src"))
    from vulcan_model_contract.validate import validate_instance, validate_resource_requirements

BACKEND_NAME = "ray-serve"
BACKEND_VERSION = "0.3.0"
RESOURCES_PATH = Path(__file__).resolve().parent / "resource-requirements.json"

api = FastAPI(title="Vulcan Ray Serve contract surface", docs_url=None, redoc_url=None)
try:
    from vulcan_serving_common.otel import instrument_fastapi
except ImportError:  # pragma: no cover
    from otel_setup import instrument_fastapi  # type: ignore

instrument_fastapi(api, BACKEND_NAME)


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


@serve.deployment(
    name="vulcan-ray-serve",
    num_replicas=1,
    ray_actor_options={"num_cpus": 1},
    max_ongoing_requests=8,
)
@serve.ingress(api)
class VulcanRayService:
    """Ray Serve deployment hosting both phase-1 reference models behind the Vulcan contract."""

    def __init__(self) -> None:
        self._ready = False
        # Per-replica registry avoids Prometheus duplicate registration across Ray workers.
        self._registry = CollectorRegistry()
        self._infer_requests = Counter(
            "vulcan_infer_requests_total",
            "Total /v1/infer requests",
            ["backend", "status", "modality"],
            registry=self._registry,
        )
        self._infer_latency = Histogram(
            "vulcan_infer_latency_seconds",
            "Inference latency seconds",
            ["backend", "modality"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
            registry=self._registry,
        )
        # Prime labeled series so /metrics has samples before the first /v1/infer
        # (conformance suite checks Prometheus sample lines, not only HELP/TYPE).
        for status, modality in (
            ("ok", "llm"),
            ("ok", "vision"),
            ("error", "unknown"),
            ("error", "llm"),
            ("error", "vision"),
        ):
            self._infer_requests.labels(BACKEND_NAME, status, modality)
        self._infer_latency.labels(BACKEND_NAME, "llm")
        self._infer_latency.labels(BACKEND_NAME, "vision")
        self._llm = load_llm()
        self._vision = load_vision()
        self._ready = True

    @api.get("/health")
    def health(self) -> JSONResponse:
        status = "ok" if self._ready else "starting"
        payload = {
            "status": status,
            "backend": BACKEND_NAME,
            "model_id": LLM_MODEL_ID,
            "version": BACKEND_VERSION,
            "mode": _runtime_mode(),
            "detail": f"models={LLM_MODEL_ID},{VISION_MODEL_ID};replicas=ray-serve",
        }
        validate_instance(payload, "health")
        return JSONResponse(status_code=200 if self._ready else 503, content=payload)

    @api.get("/metrics")
    def metrics(self) -> PlainTextResponse:
        return PlainTextResponse(
            generate_latest(self._registry).decode("utf-8"),
            media_type=CONTENT_TYPE_LATEST,
        )

    @api.get("/v1/resources")
    def resources(self) -> dict[str, Any]:
        return _load_resources()

    @api.post("/v1/infer")
    async def infer(self, request: Request) -> JSONResponse:
        if not self._ready:
            return _error(503, "not_ready", "backend starting")

        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            self._infer_requests.labels(BACKEND_NAME, "error", "unknown").inc()
            return _error(400, "invalid_json", "body must be JSON")

        if not isinstance(payload, dict):
            self._infer_requests.labels(BACKEND_NAME, "error", "unknown").inc()
            return _error(400, "invalid_request", "body must be a JSON object")

        request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) else None
        try:
            validate_instance(payload, "infer-request")
        except Exception as exc:  # noqa: BLE001
            self._infer_requests.labels(
                BACKEND_NAME, "error", str(payload.get("modality", "unknown"))
            ).inc()
            return _error(400, "invalid_request", str(exc), request_id)

        modality = payload["modality"]
        model_id = payload["model_id"]
        started = time.perf_counter()
        try:
            if modality == "llm":
                if model_id != LLM_MODEL_ID:
                    raise ValueError(f"unknown llm model_id: {model_id}")
                inp = payload["input"]
                output = self._llm.generate(
                    messages=inp["messages"],
                    max_tokens=int(inp.get("max_tokens") or 16),
                    temperature=float(inp.get("temperature") or 0.0),
                )
            elif modality == "vision":
                if model_id != VISION_MODEL_ID:
                    raise ValueError(f"unknown vision model_id: {model_id}")
                inp = payload["input"]
                output = self._vision.classify(
                    images=inp["images"],
                    prompt=inp.get("prompt"),
                )
            else:  # pragma: no cover
                raise ValueError(f"unsupported modality: {modality}")
        except Exception as exc:  # noqa: BLE001
            self._infer_requests.labels(BACKEND_NAME, "error", modality).inc()
            return _error(400, "infer_failed", str(exc), request_id)

        latency_ms = (time.perf_counter() - started) * 1000.0
        self._infer_latency.labels(BACKEND_NAME, modality).observe(latency_ms / 1000.0)
        self._infer_requests.labels(BACKEND_NAME, "ok", modality).inc()
        response = {
            "request_id": payload["request_id"],
            "modality": modality,
            "model_id": model_id,
            "output": output,
            "latency_ms": latency_ms,
        }
        validate_instance(response, "infer-response")
        return JSONResponse(status_code=200, content=response)


# `serve run service:app` entrypoint
app = VulcanRayService.bind()


def main() -> None:
    """Run the deployment in-process (used by Docker entrypoint)."""
    import ray

    port = int(os.environ.get("PORT", "9002"))
    host = os.environ.get("HOST", "0.0.0.0")
    if not ray.is_initialized():
        ray.init(
            ignore_reinit_error=True,
            include_dashboard=False,
            num_cpus=int(os.environ.get("RAY_NUM_CPUS", "2")),
        )
    serve.start(detached=False, http_options={"host": host, "port": port})
    serve.run(app, name="vulcan-ray-serve", route_prefix="/", blocking=True)


if __name__ == "__main__":
    main()
