"""Tool: read real benchmark/results JSON (ADR-014)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from advisor.non_fabrication import EvidenceItem, add_backend, add_number


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def benchmark_dir() -> Path:
    env = os.environ.get("VULCAN_BENCHMARK_DIR")
    if env:
        return Path(env)
    return repo_root() / "benchmark" / "results"


def read_benchmark_results(
    *,
    directory: Path | None = None,
    evidence: list[EvidenceItem] | None = None,
) -> dict[str, Any]:
    """Load every ``*-cpu.json`` result file (schema used since phases 0–17)."""
    root = directory or benchmark_dir()
    files: list[dict[str, Any]] = []
    for path in sorted(root.glob("*-cpu.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        backend = str(data.get("backend") or path.stem)
        metrics = data.get("metrics") or {}
        latency = metrics.get("latency_ms") or {}
        p95 = latency.get("p95")
        rps = metrics.get("throughput_rps")
        entry = {
            "path": str(path.relative_to(repo_root()) if path.is_relative_to(repo_root()) else path),
            "backend": backend,
            "model_id": data.get("model_id"),
            "modality": data.get("modality"),
            "runtime_mode": data.get("runtime_mode"),
            "latency_ms_p95": p95,
            "throughput_rps": rps,
            "error_rate": metrics.get("error_rate"),
        }
        files.append(entry)
        if evidence is not None:
            add_backend(evidence, "read_benchmark_results", f"backend:{backend}", backend)
            if p95 is not None:
                add_number(evidence, "read_benchmark_results", f"p95_ms:{backend}", float(p95))
            if rps is not None:
                add_number(evidence, "read_benchmark_results", f"rps:{backend}", float(rps))
            if metrics.get("error_rate") is not None:
                add_number(
                    evidence,
                    "read_benchmark_results",
                    f"error_rate:{backend}",
                    float(metrics["error_rate"]),
                )
    return {"directory": str(root), "results": files, "count": len(files)}
