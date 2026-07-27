"""Offline unit tests for advisor grounding (ADR-014)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from advisor.non_fabrication import (
    EvidenceItem,
    add_backend,
    add_number,
    assert_answer_grounded,
    extract_numbers,
)
from advisor.recommend import synthesize_recommendation
from advisor.tools_benchmarks import read_benchmark_results


ROOT = Path(__file__).resolve().parents[2]


def test_read_benchmark_results_real_files() -> None:
    evidence: list[EvidenceItem] = []
    out = read_benchmark_results(evidence=evidence)
    assert out["count"] >= 1
    backends = {r["backend"] for r in out["results"]}
    assert "bentoml" in backends
    assert any(e.kind == "number" and e.tool == "read_benchmark_results" for e in evidence)
    # Every recorded p95 must match the file.
    by_backend = {r["backend"]: r for r in out["results"]}
    for e in evidence:
        if e.key.startswith("p95_ms:"):
            b = e.key.split(":", 1)[1]
            assert abs(float(e.value) - float(by_backend[b]["latency_ms_p95"])) < 1e-9


def test_non_fabrication_rejects_invented_number() -> None:
    evidence: list[EvidenceItem] = []
    add_backend(evidence, "t", "b", "bentoml")
    add_number(evidence, "t", "cost", 0.001)
    with pytest.raises(AssertionError, match="non-fabrication FAIL"):
        assert_answer_grounded("recommend_backend=bentoml cost_usd_per_token=999.0", evidence)


def test_non_fabrication_rejects_invented_backend() -> None:
    evidence: list[EvidenceItem] = []
    add_backend(evidence, "t", "b", "bentoml")
    add_number(evidence, "t", "cost", 0.001)
    with pytest.raises(AssertionError, match="backend"):
        assert_answer_grounded("recommend_backend=triton cost_usd_per_token=0.001", evidence)


def test_template_recommend_grounded_from_benchmarks() -> None:
    evidence: list[EvidenceItem] = []
    benches = read_benchmark_results(evidence=evidence)
    # Simulate empty prometheus so recommend uses benchmark lowest p95.
    prom = {"cost_per_token": {"series": []}, "catalog_latency_p95_ms": {"series": []}}
    routing = {"selected_backend": "bentoml", "fallback": False}
    add_backend(evidence, "query_routing_history", "selected_backend", "bentoml")
    from advisor.non_fabrication import add_bool

    add_bool(evidence, "query_routing_history", "fallback", False)
    out = synthesize_recommendation(
        question="which backend should I use for lowest cost per token right now?",
        prometheus=prom,
        benchmarks=benches,
        routing=routing,
        evidence=evidence,
        use_local_llm=False,
    )
    assert out["answer"]
    assert out["recommendation"]["backend"] in {r["backend"] for r in benches["results"]}
    assert_answer_grounded(out["answer"], evidence)
    nums = extract_numbers(out["answer"])
    assert nums, "expected numeric claims in answer"
    allowed = {e.value_str for e in evidence if e.kind == "number"}
    for n in nums:
        assert n in allowed or any(abs(float(n) - float(e.value)) < 1e-9 for e in evidence if e.kind == "number")


@pytest.mark.skipif(not os.environ.get("VULCAN_ADVISOR_LIVE"), reason="live Prom/gateway not enabled")
def test_full_graph_live_non_fabrication() -> None:
    from advisor.graph import run_advisor

    # Weights may be missing until export; commentary is optional for the grounding bar.
    use_llm = (ROOT / "models/artifacts/llm/gpt2-small/model.safetensors").is_file()
    result = run_advisor(
        "which backend should I use for lowest cost per token right now?",
        use_local_llm=use_llm,
    )
    evidence = [
        EvidenceItem(
            tool=e["tool"],
            kind=e["kind"],
            key=e["key"],
            value=e["value"],
            value_str=e["value_str"],
        )
        for e in result["evidence"]
    ]
    assert result.get("prometheus", {}).get("cost_per_token", {}).get("count", 0) >= 1
    assert result.get("benchmarks", {}).get("count", 0) >= 1
    assert result.get("routing", {}).get("selected_backend")
    assert_answer_grounded(result["answer"], evidence)
    # Every number in the answer must equal a tool-returned value from this run.
    tool_nums = {e.value_str for e in evidence if e.kind == "number"}
    for token in extract_numbers(result["answer"]):
        assert token in tool_nums or any(
            abs(float(token) - float(e.value)) <= max(1e-12, abs(float(e.value)) * 1e-9)
            for e in evidence
            if e.kind == "number"
        )
