"""Vulcan Triton contract shim — phase-0 HTTP surface over Triton Inference Server."""

from __future__ import annotations

import base64
import io
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
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
    from shim.triton_http import TritonHttpClient, TritonHttpError
except ImportError:  # pragma: no cover — `python shim/service.py`
    from triton_http import TritonHttpClient, TritonHttpError  # type: ignore[no-redef]

try:
    from vulcan_model_contract.validate import validate_instance, validate_resource_requirements
except ImportError:  # pragma: no cover
    import sys

    ROOT = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(ROOT / "contracts" / "model-contract" / "src"))
    from vulcan_model_contract.validate import validate_instance, validate_resource_requirements

BACKEND_NAME = "triton"
BACKEND_VERSION = "0.4.0"
LLM_MODEL_ID = "reference-tiny-llm"
VISION_MODEL_ID = "reference-tiny-vision"
TRITON_LLM = "reference_tiny_llm"
TRITON_VISION = "reference_tiny_vision"

ROOT = Path(__file__).resolve().parents[3]
RESOURCES_PATH = Path(__file__).resolve().parents[1] / "resource-requirements.json"
LABELS_PATH = ROOT / "models" / "artifacts" / "vision" / "resnet18" / "imagenet_classes.json"
PREPROCESS_PATH = ROOT / "models" / "artifacts" / "vision" / "resnet18" / "preprocess.json"
TOKENIZER_PATH = ROOT / "models" / "artifacts" / "llm" / "gpt2-small"

app = FastAPI(title="Vulcan Triton contract shim", docs_url=None, redoc_url=None)
try:
    from vulcan_serving_common.otel import instrument_fastapi
except ImportError:  # pragma: no cover
    from otel_setup import instrument_fastapi  # type: ignore

instrument_fastapi(app, BACKEND_NAME)

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
    ("ok", "vision"),
    ("error", "unknown"),
    ("error", "llm"),
    ("error", "vision"),
):
    _infer_requests.labels(BACKEND_NAME, _status, _modality)
_infer_latency.labels(BACKEND_NAME, "llm")
_infer_latency.labels(BACKEND_NAME, "vision")

_tokenizer = None
_labels: list[str] = []
_preprocess: dict[str, Any] = {}
_ready = False


def _triton_url() -> str:
    return os.environ.get("TRITON_URL", "127.0.0.1:8000")


def _runtime_mode() -> str:
    return "gpu" if os.environ.get("VULCAN_RUNTIME_MODE", "cpu").lower() == "gpu" else "cpu"


def _client() -> TritonHttpClient:
    return TritonHttpClient(_triton_url())


def _load_resources() -> dict[str, Any]:
    data = json.loads(RESOURCES_PATH.read_text(encoding="utf-8"))
    validate_resource_requirements(data)
    return data


def _error(status: int, error: str, message: str, request_id: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": error, "message": message}
    if request_id is not None:
        body["request_id"] = request_id
    return JSONResponse(status_code=status, content=body)


def _ensure_side_assets() -> None:
    global _tokenizer, _labels, _preprocess
    if _tokenizer is None:
        from transformers import AutoTokenizer

        tok_path = Path(os.environ.get("VULCAN_TOKENIZER_DIR", str(TOKENIZER_PATH)))
        _tokenizer = AutoTokenizer.from_pretrained(str(tok_path), local_files_only=True)
        if _tokenizer.pad_token is None:
            _tokenizer.pad_token = _tokenizer.eos_token
    if not _labels:
        labels_path = Path(os.environ.get("VULCAN_LABELS_PATH", str(LABELS_PATH)))
        _labels = json.loads(labels_path.read_text(encoding="utf-8"))
    if not _preprocess:
        prep_path = Path(os.environ.get("VULCAN_PREPROCESS_PATH", str(PREPROCESS_PATH)))
        _preprocess = json.loads(prep_path.read_text(encoding="utf-8"))


def _triton_ready() -> bool:
    client = _client()
    try:
        if not client.is_server_live() or not client.is_server_ready():
            return False
        return client.is_model_ready(TRITON_LLM) and client.is_model_ready(TRITON_VISION)
    except Exception:  # noqa: BLE001
        return False
    finally:
        client.close()


def _infer_llm(messages: list[dict[str, str]], max_tokens: int, temperature: float) -> dict[str, Any]:
    _ensure_side_assets()
    assert _tokenizer is not None
    prompt_parts = [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages]
    prompt_parts.append("assistant:")
    prompt = "\n".join(prompt_parts)
    encoded = _tokenizer(prompt, return_tensors="np")
    input_ids = encoded["input_ids"].astype(np.int64)
    attention_mask = encoded["attention_mask"].astype(np.int64)
    prompt_len = int(input_ids.shape[-1])
    eos_id = int(_tokenizer.eos_token_id)
    generated: list[int] = []
    client = _client()
    try:
        for _ in range(max(1, int(max_tokens))):
            outs = client.infer(
                TRITON_LLM,
                {"input_ids": input_ids, "attention_mask": attention_mask},
                ["logits"],
            )
            logits = outs["logits"]  # [batch, seq, vocab]
            last = logits[0, -1, :]
            if temperature and temperature > 0:
                probs = np.exp(last / float(temperature))
                probs = probs / np.sum(probs)
                next_id = int(np.random.choice(len(probs), p=probs))
            else:
                next_id = int(np.argmax(last))
            if next_id == eos_id:
                break
            generated.append(next_id)
            next_arr = np.array([[next_id]], dtype=np.int64)
            input_ids = np.concatenate([input_ids, next_arr], axis=1)
            attention_mask = np.concatenate(
                [attention_mask, np.ones((1, 1), dtype=np.int64)], axis=1
            )
    finally:
        client.close()

    text = _tokenizer.decode(generated, skip_special_tokens=True).strip()
    completion = len(generated)
    return {
        "text": text or "",
        "finish_reason": "stop",
        "usage": {
            "prompt_tokens": prompt_len,
            "completion_tokens": completion,
            "total_tokens": prompt_len + completion,
        },
    }


def _infer_vision(images: list[dict[str, str]], prompt: str | None) -> dict[str, Any]:
    from PIL import Image

    _ensure_side_assets()
    crop = int(_preprocess.get("crop") or 224)
    mean = np.array(_preprocess.get("mean") or [0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array(_preprocess.get("std") or [0.229, 0.224, 0.225], dtype=np.float32)
    raw = base64.b64decode(images[0]["data_base64"])
    image = Image.open(io.BytesIO(raw)).convert("RGB").resize((crop, crop), Image.BILINEAR)
    arr = np.asarray(image).astype(np.float32) / 255.0
    arr = (arr - mean) / std
    tensor = np.transpose(arr, (2, 0, 1))[None, ...].astype(np.float32)

    client = _client()
    try:
        outs = client.infer(TRITON_VISION, {"pixel_values": tensor}, ["logits"])
        logits = outs["logits"][0]
    finally:
        client.close()

    exp = np.exp(logits - np.max(logits))
    probs = exp / np.sum(exp)
    top_idx = int(np.argmax(probs))
    label = _labels[top_idx] if top_idx < len(_labels) else str(top_idx)
    score = float(probs[top_idx])
    text = f"{label} ({score:.3f})"
    if prompt:
        text = f"{prompt.strip()}: {text}"
    return {
        "text": text,
        "labels": [{"name": label, "score": score}],
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _wait_for_triton() -> None:
    global _ready
    wait_secs = float(os.environ.get("TRITON_WAIT_SECONDS", "300"))
    deadline = time.time() + wait_secs
    while time.time() < deadline:
        if _triton_ready():
            try:
                _ensure_side_assets()
            except Exception as exc:  # noqa: BLE001
                print(f"triton shim: side assets not ready yet: {exc}", flush=True)
                time.sleep(2)
                continue
            _ready = True
            print(
                f"triton shim: ready (engine={_triton_url()}; "
                f"models={TRITON_LLM},{TRITON_VISION})",
                flush=True,
            )
            return
        time.sleep(2)
    _ready = False
    print(
        f"triton shim: ERROR — readiness timed out after {wait_secs:.0f}s "
        f"(engine={_triton_url()}; expected READY models "
        f"{TRITON_LLM}+{TRITON_VISION}). /health will stay 503. "
        "Check: docker compose logs triton-engine",
        flush=True,
    )


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=_wait_for_triton, name="triton-wait", daemon=True).start()


@app.get("/health")
def health() -> JSONResponse:
    ready = _ready and _triton_ready()
    payload = {
        "status": "ok" if ready else "starting",
        "backend": BACKEND_NAME,
        "model_id": LLM_MODEL_ID,
        "version": BACKEND_VERSION,
        "mode": _runtime_mode(),
        "detail": f"triton={_triton_url()};models={LLM_MODEL_ID},{VISION_MODEL_ID}",
    }
    validate_instance(payload, "health")
    return JSONResponse(status_code=200 if ready else 503, content=payload)


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(_registry).decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/resources")
def resources() -> dict[str, Any]:
    return _load_resources()


@app.post("/v1/infer")
async def infer(request: Request) -> JSONResponse:
    if not (_ready and _triton_ready()):
        return _error(503, "not_ready", "triton backend starting")

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
    started = time.perf_counter()
    try:
        if modality == "llm":
            if model_id != LLM_MODEL_ID:
                raise ValueError(f"unknown llm model_id: {model_id}")
            inp = payload["input"]
            output = _infer_llm(
                messages=inp["messages"],
                max_tokens=int(inp.get("max_tokens") or 16),
                temperature=float(inp.get("temperature") or 0.0),
            )
        elif modality == "vision":
            if model_id != VISION_MODEL_ID:
                raise ValueError(f"unknown vision model_id: {model_id}")
            inp = payload["input"]
            output = _infer_vision(images=inp["images"], prompt=inp.get("prompt"))
        else:  # pragma: no cover
            raise ValueError(f"unsupported modality: {modality}")
    except TritonHttpError as exc:
        _infer_requests.labels(BACKEND_NAME, "error", modality).inc()
        return _error(400, "infer_failed", str(exc), request_id)
    except Exception as exc:  # noqa: BLE001
        _infer_requests.labels(BACKEND_NAME, "error", modality).inc()
        return _error(400, "infer_failed", str(exc), request_id)

    latency_ms = (time.perf_counter() - started) * 1000.0
    _infer_latency.labels(BACKEND_NAME, modality).observe(latency_ms / 1000.0)
    _infer_requests.labels(BACKEND_NAME, "ok", modality).inc()
    response = {
        "request_id": payload["request_id"],
        "modality": modality,
        "model_id": model_id,
        "output": output,
        "latency_ms": latency_ms,
    }
    validate_instance(response, "infer-response")
    return JSONResponse(status_code=200, content=response)


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "9003"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
