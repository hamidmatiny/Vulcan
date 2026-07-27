#!/usr/bin/env python3
"""Expose routing cost/latency gauges from the same files gateway/ reads (ADR-006).

Also emits clearly labeled GPU utilization *placeholder* series for CPU-mode compose
demos (ADR-002 — not live GPU hardware).
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest

REGISTRY = CollectorRegistry()

LATENCY_P95 = Gauge(
    "vulcan_routing_latency_p95_ms",
    "Recorded p95 latency from benchmark/results (same source as gateway catalog)",
    ["backend", "modality", "source"],
    registry=REGISTRY,
)
COST_PER_1K = Gauge(
    "vulcan_routing_cost_usd_per_1k_tokens",
    "Recorded $/1k tokens from bedrock pricing-reference (blended input+output / 2)",
    ["backend", "model_id", "source"],
    registry=REGISTRY,
)
COST_PER_INFER = Gauge(
    "vulcan_estimated_cost_per_inference_usd",
    "Illustrative cost for a 1k-in+1k-out request using pricing-reference blend",
    ["backend", "model_id", "source"],
    registry=REGISTRY,
)
GPU_UTIL = Gauge(
    "vulcan_gpu_utilization_ratio",
    "GPU utilization 0-1. PLACEHOLDER in CPU compose — not from real GPU hardware (ADR-002)",
    ["backend", "gpu", "data_source"],
    registry=REGISTRY,
)
EXPORTER_INFO = Gauge(
    "vulcan_cost_exporter_info",
    "Cost exporter metadata (always 1)",
    ["mode"],
    registry=REGISTRY,
)


def _load_benchmarks(dir_path: Path) -> None:
    if not dir_path.is_dir():
        return
    for path in sorted(dir_path.glob("*-cpu.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        backend = data.get("backend")
        modality = data.get("modality")
        p95 = (data.get("metrics") or {}).get("latency_ms", {}).get("p95")
        if not backend or modality != "llm" or p95 is None:
            continue
        if backend == "gateway":
            continue
        LATENCY_P95.labels(backend, modality, f"benchmark/results/{path.name}").set(float(p95))


def _load_bedrock(path: Path) -> None:
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("source") != "static_reference":
        return
    models = data.get("models") or {}
    # Same default candidate as gateway/internal/catalog/catalog.go
    model_id = "amazon.titan-text-express-v1"
    model = models.get(model_id)
    if not model:
        return
    blend = (float(model["input_usd_per_1k_tokens"]) + float(model["output_usd_per_1k_tokens"])) / 2.0
    p95 = float(model["typical_latency_ms"]["p95"])
    src = "bedrock-gateway/pricing-reference.json"
    LATENCY_P95.labels("bedrock", "llm", src).set(p95)
    COST_PER_1K.labels("bedrock", model_id, src).set(blend)
    # 1k in + 1k out → 2k tokens at blend-per-1k ≈ input+output rates sum for that shape
    COST_PER_INFER.labels("bedrock", model_id, src).set(
        float(model["input_usd_per_1k_tokens"]) + float(model["output_usd_per_1k_tokens"])
    )


def _load_gpu_placeholders() -> None:
    """Demo series only — labeled so dashboards can filter live vs placeholder."""
    for backend, util in (
        ("bentoml", 0.12),
        ("ray-serve", 0.18),
        ("triton", 0.41),
        ("vllm", 0.55),
        ("kserve", 0.33),
    ):
        GPU_UTIL.labels(backend, "GPU-0", "placeholder_cpu_compose").set(util)


def refresh() -> None:
    bench = Path(os.environ.get("VULCAN_BENCHMARK_DIR", "/benchmarks"))
    pricing = Path(os.environ.get("VULCAN_BEDROCK_PRICING", "/pricing/pricing-reference.json"))
    _load_benchmarks(bench)
    _load_bedrock(pricing)
    _load_gpu_placeholders()
    EXPORTER_INFO.labels(os.environ.get("VULCAN_RUNTIME_MODE", "cpu")).set(1)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/metrics", "/"):
            self.send_response(404)
            self.end_headers()
            return
        refresh()
        body = generate_latest(REGISTRY)
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> None:
    refresh()
    port = int(os.environ.get("PORT", "9100"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"vulcan cost-exporter on :{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
