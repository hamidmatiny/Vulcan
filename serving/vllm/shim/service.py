"""Vulcan vLLM contract shim — phase-0 HTTP surface over OpenAI-compatible engine."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

try:
    from vulcan_model_contract.validate import validate_instance, validate_resource_requirements
except ImportError:  # pragma: no cover
    import sys

    ROOT = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(ROOT / "contracts" / "model-contract" / "src"))
    from vulcan_model_contract.validate import validate_instance, validate_resource_requirements

BACKEND_NAME = "vllm"
BACKEND_VERSION = "0.5.0"
LLM_MODEL_ID = "reference-tiny-llm"
RESOURCES_PATH = Path(__file__).resolve().parents[1] / "resource-requirements.json"

app = FastAPI(title="Vulcan vLLM contract shim", docs_url=None, redoc_url=None)

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

_ready = False


def _engine_url() -> str:
    raw = os.environ.get("VLLM_URL", "http://127.0.0.1:8000")
    return raw if "://" in raw else f"http://{raw}"


def _runtime_mode() -> str:
    return "gpu" if os.environ.get("VULCAN_RUNTIME_MODE", "cpu").lower() == "gpu" else "cpu"


def _load_resources() -> dict[str, Any]:
    data = json.loads(RESOURCES_PATH.read_text(encoding="utf-8"))
    validate_resource_requirements(data)
    return data


def _error(status: int, error: str, message: str, request_id: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": error, "message": message}
    if request_id is not None:
        body["request_id"] = request_id
    return JSONResponse(status_code=status, content=body)


def _engine_ready() -> bool:
    try:
        with httpx.Client(base_url=_engine_url(), timeout=5.0) as client:
            resp = client.get("/v1/models")
            return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _wait_for_engine() -> None:
    global _ready
    wait_secs = float(os.environ.get("VLLM_WAIT_SECONDS", "300"))
    deadline = time.time() + wait_secs
    while time.time() < deadline:
        if _engine_ready():
            _ready = True
            print(f"vllm shim: ready (engine={_engine_url()})", flush=True)
            return
        time.sleep(2)
    _ready = False
    print(
        f"vllm shim: ERROR — engine readiness timed out after {wait_secs:.0f}s "
        f"(engine={_engine_url()}). /health will stay 503. "
        "Check: docker compose logs vllm-engine",
        flush=True,
    )


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=_wait_for_engine, name="vllm-wait", daemon=True).start()


@app.get("/health")
def health() -> JSONResponse:
    ready = _ready and _engine_ready()
    payload = {
        "status": "ok" if ready else "starting",
        "backend": BACKEND_NAME,
        "model_id": LLM_MODEL_ID,
        "version": BACKEND_VERSION,
        "mode": _runtime_mode(),
        "detail": f"engine={_engine_url()};modalities=llm;vision=unsupported",
    }
    validate_instance(payload, "health")
    return JSONResponse(status_code=200 if ready else 503, content=payload)


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(_registry).decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/resources")
def resources() -> dict[str, Any]:
    return _load_resources()


def _infer_llm(messages: list[dict[str, str]], max_tokens: int, temperature: float) -> dict[str, Any]:
    payload = {
        "model": LLM_MODEL_ID,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    with httpx.Client(base_url=_engine_url(), timeout=120.0) as client:
        resp = client.post("/v1/chat/completions", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"engine chat completions failed: {resp.status_code} {resp.text[:400]}")
        data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    text = message.get("content") if isinstance(message.get("content"), str) else ""
    usage = data.get("usage") or {}
    return {
        "text": text or "",
        "finish_reason": choice.get("finish_reason") or "stop",
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        },
    }


@app.post("/v1/infer")
async def infer(request: Request) -> JSONResponse:
    if not (_ready and _engine_ready()):
        return _error(503, "not_ready", "vllm backend starting")

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

    # LLM-only: vision is an explicit unsupported contract error (not a silent failure).
    if modality == "vision":
        _infer_requests.labels(BACKEND_NAME, "unsupported", "vision").inc()
        return _error(
            400,
            "unsupported_modality",
            "serving/vllm is LLM-only; vision is not implemented on this adapter "
            "(use bentoml, ray-serve, or triton for reference-tiny-vision)",
            request_id,
        )

    if modality != "llm":
        _infer_requests.labels(BACKEND_NAME, "error", "unknown").inc()
        return _error(400, "invalid_request", f"unsupported modality: {modality}", request_id)

    if model_id != LLM_MODEL_ID:
        _infer_requests.labels(BACKEND_NAME, "error", "llm").inc()
        return _error(400, "invalid_request", f"unknown llm model_id: {model_id}", request_id)

    started = time.perf_counter()
    try:
        inp = payload["input"]
        output = _infer_llm(
            messages=inp["messages"],
            max_tokens=int(inp.get("max_tokens") or 16),
            temperature=float(inp.get("temperature") or 0.0),
        )
    except Exception as exc:  # noqa: BLE001
        _infer_requests.labels(BACKEND_NAME, "error", "llm").inc()
        return _error(400, "infer_failed", str(exc), request_id)

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
    port = int(os.environ.get("PORT", "9004"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
