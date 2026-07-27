#!/usr/bin/env python3
"""Expose routing cost/latency + cost-per-token from ADR-006 / ADR-008 sources.

Does NOT emit GPU utilization — that lives in observability/gpu-metrics/ (DCGM or
synthetic DCGM-shaped exporter).
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
    "Estimated $/1k tokens (Bedrock pricing-reference or self-hosted ADR-008 formula)",
    ["backend", "model_id", "source"],
    registry=REGISTRY,
)
COST_PER_TOKEN = Gauge(
    "vulcan_estimated_cost_usd_per_token",
    "Estimated $/token (Bedrock pricing-reference or self-hosted ADR-008 formula)",
    ["backend", "model_id", "instance_type", "source"],
    registry=REGISTRY,
)
COST_PER_INFER = Gauge(
    "vulcan_estimated_cost_per_inference_usd",
    "Illustrative cost for a 1k-in+1k-out (Bedrock) or assumed_tokens_per_request (self-hosted)",
    ["backend", "model_id", "source"],
    registry=REGISTRY,
)
GPU_HOUR_USD = Gauge(
    "vulcan_gpu_hour_assumption_usd",
    "Documented $/GPU-hour assumption (static_reference_assumption — not an invoice)",
    ["instance_type", "source"],
    registry=REGISTRY,
)
EXPORTER_INFO = Gauge(
    "vulcan_cost_exporter_info",
    "Cost exporter metadata (always 1)",
    ["mode"],
    registry=REGISTRY,
)

_BENCH_THROUGHPUT: dict[str, tuple[float, str, str]] = {}


def _load_benchmarks(dir_path: Path) -> None:
    global _BENCH_THROUGHPUT
    _BENCH_THROUGHPUT = {}
    if not dir_path.is_dir():
        return
    for path in sorted(dir_path.glob("*-cpu.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        backend = data.get("backend")
        modality = data.get("modality")
        metrics = data.get("metrics") or {}
        p95 = (metrics.get("latency_ms") or {}).get("p95")
        thr = metrics.get("throughput_rps")
        if not backend or modality != "llm" or p95 is None:
            continue
        if backend == "gateway":
            continue
        src = f"benchmark/results/{path.name}"
        LATENCY_P95.labels(backend, modality, src).set(float(p95))
        model_id = str(data.get("model_id") or "reference-tiny-llm")
        if thr is not None and float(thr) > 0:
            _BENCH_THROUGHPUT[backend] = (float(thr), src, model_id)


def _load_gpu_hour_assumptions(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("source") != "static_reference_assumption":
        return {}
    src = "observability/cost-exporter/gpu-hour-assumptions.json"
    for itype, meta in (data.get("instance_types") or {}).items():
        rate = meta.get("usd_per_gpu_hour")
        if rate is None:
            continue
        GPU_HOUR_USD.labels(itype, src).set(float(rate))
    return data


def _apply_self_hosted_cost_per_token(assumptions: dict) -> None:
    if not assumptions or not _BENCH_THROUGHPUT:
        return
    src_assump = "observability/cost-exporter/gpu-hour-assumptions.json"
    itype = assumptions.get("default_instance_type_for_self_hosted_inference") or "g5.xlarge"
    types = assumptions.get("instance_types") or {}
    meta = types.get(itype) or {}
    usd_hr = meta.get("usd_per_gpu_hour")
    t_req = float(assumptions.get("assumed_tokens_per_request") or 16)
    if usd_hr is None or t_req <= 0:
        return
    usd_per_sec = float(usd_hr) / 3600.0
    for backend, (thr, bench_src, model_id) in _BENCH_THROUGHPUT.items():
        tokens_per_sec = thr * t_req
        if tokens_per_sec <= 0:
            continue
        per_token = usd_per_sec / tokens_per_sec
        source = f"{bench_src}+{src_assump}"
        COST_PER_TOKEN.labels(backend, model_id, itype, source).set(per_token)
        COST_PER_1K.labels(backend, model_id, source).set(per_token * 1000.0)
        COST_PER_INFER.labels(backend, model_id, source).set(per_token * t_req)


def _load_bedrock(path: Path) -> None:
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("source") != "static_reference":
        return
    models = data.get("models") or {}
    model_id = "amazon.titan-text-express-v1"
    model = models.get(model_id)
    if not model:
        return
    blend = (float(model["input_usd_per_1k_tokens"]) + float(model["output_usd_per_1k_tokens"])) / 2.0
    p95 = float(model["typical_latency_ms"]["p95"])
    src = "bedrock-gateway/pricing-reference.json"
    LATENCY_P95.labels("bedrock", "llm", src).set(p95)
    COST_PER_1K.labels("bedrock", model_id, src).set(blend)
    COST_PER_TOKEN.labels("bedrock", model_id, "bedrock", src).set(blend / 1000.0)
    COST_PER_INFER.labels("bedrock", model_id, src).set(
        float(model["input_usd_per_1k_tokens"]) + float(model["output_usd_per_1k_tokens"])
    )


def refresh() -> None:
    # Clear labeled series by recreating is hard with prometheus_client; set on refresh is fine
    # for static catalogs (values overwrite).
    bench = Path(os.environ.get("VULCAN_BENCHMARK_DIR", "/benchmarks"))
    pricing = Path(os.environ.get("VULCAN_BEDROCK_PRICING", "/pricing/pricing-reference.json"))
    assumptions_path = Path(
        os.environ.get(
            "VULCAN_GPU_HOUR_ASSUMPTIONS",
            str(Path(__file__).resolve().parent / "gpu-hour-assumptions.json"),
        )
    )
    _load_benchmarks(bench)
    assumptions = _load_gpu_hour_assumptions(assumptions_path)
    _apply_self_hosted_cost_per_token(assumptions)
    _load_bedrock(pricing)
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
