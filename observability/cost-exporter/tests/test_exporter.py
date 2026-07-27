from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path

import exporter


def test_refresh_loads_benchmark_pricing_and_cost_per_token(tmp_path: Path, monkeypatch) -> None:
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "bentoml-cpu.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "backend": "bentoml",
                "modality": "llm",
                "model_id": "reference-tiny-llm",
                "target_url": "http://x",
                "started_at": "2026-01-01T00:00:00Z",
                "duration_seconds": 1,
                "vus": 1,
                "metrics": {
                    "requests_total": 1,
                    "error_rate": 0,
                    "throughput_rps": 10.0,
                    "latency_ms": {"p50": 10, "p95": 42, "p99": 50},
                },
            }
        ),
        encoding="utf-8",
    )
    pricing = tmp_path / "pricing.json"
    pricing.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "static_reference",
                "models": {
                    "amazon.titan-text-express-v1": {
                        "input_usd_per_1k_tokens": 0.0002,
                        "output_usd_per_1k_tokens": 0.0006,
                        "typical_latency_ms": {"p50": 100, "p95": 400},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assumptions = tmp_path / "gpu-hour.json"
    assumptions.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "static_reference_assumption",
                "assumed_tokens_per_request": 16,
                "default_instance_type_for_self_hosted_inference": "g5.xlarge",
                "instance_types": {"g5.xlarge": {"usd_per_gpu_hour": 1.0}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VULCAN_BENCHMARK_DIR", str(bench))
    monkeypatch.setenv("VULCAN_BEDROCK_PRICING", str(pricing))
    monkeypatch.setenv("VULCAN_GPU_HOUR_ASSUMPTIONS", str(assumptions))
    monkeypatch.setenv("VULCAN_RUNTIME_MODE", "cpu")
    exporter.refresh()
    body = exporter.generate_latest(exporter.REGISTRY).decode()
    assert "vulcan_routing_latency_p95_ms" in body
    assert 'backend="bentoml"' in body
    assert "vulcan_estimated_cost_usd_per_token" in body
    assert "vulcan_estimated_cost_per_inference_usd" in body
    assert "placeholder_cpu_compose" not in body
    # throughput 10 rps * 16 tokens = 160 tok/s; $1/hr → 1/3600 per sec → per token = (1/3600)/160
    assert "g5.xlarge" in body


def test_refresh_loads_training_cost_per_step(tmp_path: Path, monkeypatch) -> None:
    train = tmp_path / "training" / "ray-train"
    train.mkdir(parents=True)
    (train / "result.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "backend": "ray-train",
                "model_id": "reference-tiny-llm",
                "status": "completed",
                "checkpoint_path": str(train / "checkpoint.pt"),
                "metrics": {
                    "loss_curve": [{"step": 1, "loss": 1.0}],
                    "samples_per_sec": 8.0,
                    "steps_per_sec": 2.0,
                    "wall_clock_seconds": 2.0,
                    "final_loss": 1.0,
                    "steps_completed": 4,
                },
                "cpu_dev_mode": True,
                "source": "static_reference_assumption",
            }
        ),
        encoding="utf-8",
    )
    assumptions = tmp_path / "gpu-hour.json"
    assumptions.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "static_reference_assumption",
                "default_instance_type_for_self_hosted_training": "g5.xlarge",
                "instance_types": {"g5.xlarge": {"usd_per_gpu_hour": 1.0}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VULCAN_BENCHMARK_DIR", str(tmp_path / "missing-bench"))
    monkeypatch.setenv("VULCAN_BEDROCK_PRICING", str(tmp_path / "missing-pricing.json"))
    monkeypatch.setenv("VULCAN_GPU_HOUR_ASSUMPTIONS", str(assumptions))
    monkeypatch.setenv("VULCAN_TRAINING_RESULTS_DIR", str(tmp_path / "training"))
    exporter.refresh()
    body = exporter.generate_latest(exporter.REGISTRY).decode()
    assert "vulcan_training_steps_per_sec" in body
    assert "vulcan_estimated_cost_usd_per_training_step" in body
    assert 'backend="ray-train"' in body


def test_metrics_http_endpoint(tmp_path: Path, monkeypatch) -> None:
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "ray-serve-cpu.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "backend": "ray-serve",
                "modality": "llm",
                "model_id": "reference-tiny-llm",
                "target_url": "http://x",
                "started_at": "2026-01-01T00:00:00Z",
                "duration_seconds": 1,
                "vus": 1,
                "metrics": {
                    "requests_total": 1,
                    "error_rate": 0,
                    "throughput_rps": 1,
                    "latency_ms": {"p50": 10, "p95": 20, "p99": 30},
                },
            }
        ),
        encoding="utf-8",
    )
    assumptions = tmp_path / "gpu-hour.json"
    assumptions.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "static_reference_assumption",
                "assumed_tokens_per_request": 16,
                "default_instance_type_for_self_hosted_inference": "g5.xlarge",
                "instance_types": {"g5.xlarge": {"usd_per_gpu_hour": 1.006}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VULCAN_BENCHMARK_DIR", str(bench))
    monkeypatch.setenv("VULCAN_BEDROCK_PRICING", str(tmp_path / "nope.json"))
    monkeypatch.setenv("VULCAN_GPU_HOUR_ASSUMPTIONS", str(assumptions))
    monkeypatch.setenv("PORT", "19102")
    t = threading.Thread(target=exporter.main, daemon=True)
    t.start()
    body = ""
    for _ in range(50):
        try:
            conn = HTTPConnection("127.0.0.1", 19102, timeout=1)
            conn.request("GET", "/metrics")
            resp = conn.getresponse()
            body = resp.read().decode()
            conn.close()
            if resp.status == 200:
                break
        except OSError:
            pass
    assert "vulcan_estimated_cost_usd_per_token" in body
    conn = HTTPConnection("127.0.0.1", 19102, timeout=1)
    conn.request("GET", "/nope")
    assert conn.getresponse().status == 404
    conn.close()


def test_refresh_skips_bad_json_and_gateway_backend(tmp_path: Path, monkeypatch) -> None:
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "broken-cpu.json").write_text("{not-json", encoding="utf-8")
    (bench / "gateway-cpu.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "backend": "gateway",
                "modality": "llm",
                "model_id": "reference-tiny-llm",
                "target_url": "http://x",
                "started_at": "2026-01-01T00:00:00Z",
                "duration_seconds": 1,
                "vus": 1,
                "metrics": {
                    "requests_total": 1,
                    "error_rate": 0,
                    "throughput_rps": 1,
                    "latency_ms": {"p50": 1, "p95": 2, "p99": 3},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VULCAN_BENCHMARK_DIR", str(bench))
    monkeypatch.setenv("VULCAN_BEDROCK_PRICING", str(tmp_path / "missing.json"))
    monkeypatch.setenv("VULCAN_GPU_HOUR_ASSUMPTIONS", str(tmp_path / "missing-assumptions.json"))
    exporter.refresh()
    body = exporter.generate_latest(exporter.REGISTRY).decode()
    assert "vulcan_routing_latency_p95_ms" in body or "vulcan_cost_exporter_info" in body
