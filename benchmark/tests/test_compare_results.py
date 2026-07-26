"""Unit tests for benchmark result comparison."""

from __future__ import annotations

import json
from pathlib import Path

from compare_results import load_result, load_schema, render_table

RESULTS = Path(__file__).resolve().parents[1] / "results"


def test_schema_loads() -> None:
    schema = load_schema()
    assert schema["title"] == "VulcanBenchmarkResult"


def test_render_table_from_fixture(tmp_path: Path) -> None:
    schema = load_schema()
    sample = {
        "schema_version": 1,
        "backend": "reference",
        "modality": "llm",
        "model_id": "reference-tiny-llm",
        "target_url": "http://127.0.0.1:8080",
        "started_at": "2026-07-26T00:00:00Z",
        "duration_seconds": 5.0,
        "vus": 2,
        "runtime_mode": "cpu",
        "metrics": {
            "requests_total": 100,
            "error_rate": 0.0,
            "throughput_rps": 20.0,
            "latency_ms": {"p50": 3.0, "p95": 8.0, "p99": 12.0, "avg": 4.0, "max": 15.0},
        },
    }
    path = tmp_path / "reference-llm.json"
    path.write_text(json.dumps(sample), encoding="utf-8")
    row = load_result(path, schema)
    md = render_table([row])
    assert "reference" in md
    assert "p95_ms" in md
    assert "20.000" in md
