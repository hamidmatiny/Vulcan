"""Trivial CPU-only contract reference server (proves conformance + benchmark harnesses).

Does **not** load real model weights — returns deterministic stub outputs that
satisfy the phase-0 OpenAPI schemas. Real backends land in later phases.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from vulcan_model_contract.validate import validate_instance, validate_resource_requirements

BACKEND_NAME = "reference"
BACKEND_VERSION = "0.1.0"
DEFAULT_LLM_MODEL = "reference-tiny-llm"
DEFAULT_VISION_MODEL = "reference-tiny-vision"

_metrics_lock = threading.Lock()
_infer_total = 0
_infer_errors = 0
_infer_latency_sum = 0.0
_ready = True


def resources_payload() -> dict[str, Any]:
    payload = {
        "model_id": DEFAULT_LLM_MODEL,
        "backend": BACKEND_NAME,
        "gpu_memory_mib": {"min": 0, "max": 0},
        "supports_mig": False,
        "supports_quantization": True,
        "cold_start_seconds": {"min": 0.01, "max": 0.5},
        "cpu_dev_mode": True,
        "notes": "Trivial reference server — no real weights loaded (phase-1 harness).",
    }
    validate_resource_requirements(payload)
    return payload


def health_payload(status: str = "ok") -> dict[str, Any]:
    payload = {
        "status": status,
        "backend": BACKEND_NAME,
        "model_id": DEFAULT_LLM_MODEL,
        "version": BACKEND_VERSION,
        "mode": "cpu",
    }
    validate_instance(payload, "health")
    return payload


def _stub_llm(request: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    messages = request["input"]["messages"]
    last = messages[-1]["content"] if messages else ""
    text = f"echo:{last[:64]}"
    response = {
        "request_id": request["request_id"],
        "modality": "llm",
        "model_id": request["model_id"],
        "output": {
            "text": text,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": max(1, len(last.split())),
                "completion_tokens": max(1, len(text.split())),
                "total_tokens": max(2, len(last.split()) + len(text.split())),
            },
        },
        "latency_ms": latency_ms,
    }
    validate_instance(response, "infer-response")
    return response


def _stub_vision(request: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    prompt = request["input"].get("prompt") or "image"
    response = {
        "request_id": request["request_id"],
        "modality": "vision",
        "model_id": request["model_id"],
        "output": {
            "text": f"stub-vision:{prompt[:48]}",
            "labels": [{"name": "tench", "score": 0.42}],
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        },
        "latency_ms": latency_ms,
    }
    validate_instance(response, "infer-response")
    return response


def metrics_text() -> str:
    with _metrics_lock:
        total = _infer_total
        errors = _infer_errors
        latency_sum = _infer_latency_sum
    return "\n".join(
        [
            "# HELP vulcan_infer_requests_total Total /v1/infer requests",
            "# TYPE vulcan_infer_requests_total counter",
            f'vulcan_infer_requests_total{{backend="{BACKEND_NAME}",status="ok"}} {total - errors}',
            f'vulcan_infer_requests_total{{backend="{BACKEND_NAME}",status="error"}} {errors}',
            "# HELP vulcan_infer_latency_seconds Inference latency sum (seconds)",
            "# TYPE vulcan_infer_latency_seconds counter",
            f'vulcan_infer_latency_seconds_sum{{backend="{BACKEND_NAME}"}} {latency_sum:.6f}',
            "# HELP vulcan_infer_in_flight In-flight infer requests",
            "# TYPE vulcan_infer_in_flight gauge",
            f'vulcan_infer_in_flight{{backend="{BACKEND_NAME}"}} 0',
            "",
        ]
    )


class ContractHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # Quiet by default; conformance/benchmarks generate noise.
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self._send(code, raw, "application/json")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            if not _ready:
                self._send_json(503, health_payload("starting"))
                return
            self._send_json(200, health_payload("ok"))
            return
        if path == "/metrics":
            body = metrics_text().encode("utf-8")
            self._send(200, body, "text/plain; version=0.0.4; charset=utf-8")
            return
        if path == "/v1/resources":
            self._send_json(200, resources_payload())
            return
        self._send_json(404, {"error": "not_found", "message": f"unknown path {path}"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/v1/infer":
            self._send_json(404, {"error": "not_found", "message": f"unknown path {path}"})
            return
        if not _ready:
            self._send_json(
                503,
                {"error": "not_ready", "message": "backend starting", "request_id": None},
            )
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            request = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._record_error()
            self._send_json(400, {"error": "invalid_json", "message": "body must be JSON"})
            return

        started = time.perf_counter()
        try:
            validate_instance(request, "infer-request")
        except Exception as exc:  # noqa: BLE001 — map to contract error
            self._record_error()
            self._send_json(
                400,
                {
                    "error": "invalid_request",
                    "message": str(exc),
                    "request_id": request.get("request_id") if isinstance(request, dict) else None,
                },
            )
            return

        modality = request.get("modality")
        try:
            latency_ms = (time.perf_counter() - started) * 1000.0
            if modality == "llm":
                # Tiny artificial delay so benchmarks see non-zero latency.
                time.sleep(0.002)
                latency_ms = (time.perf_counter() - started) * 1000.0
                response = _stub_llm(request, latency_ms)
            elif modality == "vision":
                time.sleep(0.002)
                latency_ms = (time.perf_counter() - started) * 1000.0
                response = _stub_vision(request, latency_ms)
            else:
                raise ValueError(f"unsupported modality: {modality}")
        except Exception as exc:  # noqa: BLE001
            self._record_error()
            self._send_json(
                400,
                {
                    "error": "infer_failed",
                    "message": str(exc),
                    "request_id": request.get("request_id"),
                },
            )
            return

        with _metrics_lock:
            global _infer_total, _infer_latency_sum
            _infer_total += 1
            _infer_latency_sum += latency_ms / 1000.0
        self._send_json(200, response)

    def _record_error(self) -> None:
        global _infer_total, _infer_errors
        with _metrics_lock:
            _infer_total += 1
            _infer_errors += 1


def create_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), ContractHandler)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Vulcan trivial contract reference server")
    parser.add_argument("--host", default="127.0.0.1")
    # Vulcan host port range: 9000–9099 (9001 = reference server).
    parser.add_argument("--port", type=int, default=9001)
    args = parser.parse_args(argv)
    server = create_server(args.host, args.port)
    print(f"vulcan-reference-server listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
