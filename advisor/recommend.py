"""Recommend node: template synthesis grounded in tool evidence (ADR-014)."""

from __future__ import annotations

from typing import Any

from advisor.local_llm import generate_commentary
from advisor.non_fabrication import (
    EvidenceItem,
    add_backend,
    add_number,
    assert_answer_grounded,
    format_number,
)


_SELF_HOSTED = {"bentoml", "ray-serve", "triton", "vllm"}


def _lowest_cost_from_prometheus(prom: dict[str, Any]) -> tuple[str, float] | None:
    series = (prom.get("cost_per_token") or {}).get("series") or []
    best: tuple[str, float] | None = None
    for row in series:
        backend = str(row.get("backend") or "")
        if backend not in _SELF_HOSTED:
            continue
        val = float(row["value"])
        if best is None or val < best[1]:
            best = (backend, val)
    return best


def _p95_from_benchmarks(benchmarks: dict[str, Any], backend: str) -> float | None:
    for row in benchmarks.get("results") or []:
        if row.get("backend") == backend and row.get("latency_ms_p95") is not None:
            return float(row["latency_ms_p95"])
    return None


def synthesize_recommendation(
    *,
    question: str,
    prometheus: dict[str, Any],
    benchmarks: dict[str, Any],
    routing: dict[str, Any],
    evidence: list[EvidenceItem],
    use_local_llm: bool = True,
) -> dict[str, Any]:
    """Build a grounded answer. CI asserts ``answer`` against ``evidence``."""
    lowest = _lowest_cost_from_prometheus(prometheus)
    if lowest is None:
        # Fall back: pick lowest p95 among benchmark files (still real tool data).
        best_b: str | None = None
        best_p95: float | None = None
        for row in benchmarks.get("results") or []:
            b = str(row.get("backend") or "")
            if b not in _SELF_HOSTED:
                continue
            p95 = row.get("latency_ms_p95")
            if p95 is None:
                continue
            p95f = float(p95)
            if best_p95 is None or p95f < best_p95:
                best_b, best_p95 = b, p95f
        if best_b is None:
            raise RuntimeError("no self-hosted backends found in prometheus or benchmarks")
        backend = add_backend(evidence, "recommend", "chosen_backend", best_b)
        cost_str = None
        p95_str = add_number(evidence, "recommend", "chosen_p95_ms", best_p95)  # type: ignore[arg-type]
        basis = "benchmark_lowest_p95"
    else:
        backend = add_backend(evidence, "recommend", "chosen_backend", lowest[0])
        cost_str = add_number(evidence, "recommend", "chosen_cost_per_token", lowest[1])
        p95 = _p95_from_benchmarks(benchmarks, lowest[0])
        p95_str = add_number(evidence, "recommend", "chosen_p95_ms", p95) if p95 is not None else None
        basis = "prometheus_lowest_cost_per_token"

    gw = str(routing.get("selected_backend") or "")
    fallback = bool(routing.get("fallback"))
    # routing tool already recorded these; re-add chosen references used in answer if needed
    if gw:
        add_backend(evidence, "recommend", "gateway_selected", gw)

    parts = [
        f"question_basis={basis}",
        f"recommend_backend={backend}",
    ]
    if cost_str is not None:
        parts.append(f"cost_usd_per_token={cost_str}")
    if p95_str is not None:
        parts.append(f"benchmark_latency_p95_ms={p95_str}")
    if gw:
        parts.append(f"gateway_selected_backend={gw}")
        parts.append(f"gateway_fallback={'true' if fallback else 'false'}")
    parts.append("model_id=reference-tiny-llm")
    add_backend(evidence, "recommend", "model_id", "reference-tiny-llm")

    answer = " ".join(parts)
    assert_answer_grounded(answer, evidence)

    commentary = {"ok": False, "text": "", "reason": "skipped"}
    if use_local_llm:
        # Prompt includes only grounded facts; commentary is not the CI-asserted answer.
        prompt = (
            f"Facts: {answer}\n"
            "Write a short note that the recommendation uses only measured Vulcan data.\n"
            "assistant:"
        )
        commentary = generate_commentary(prompt, max_new_tokens=16)

    return {
        "question": question,
        "recommendation": {
            "backend": backend,
            "cost_usd_per_token": float(cost_str) if cost_str is not None else None,
            "benchmark_latency_p95_ms": float(p95_str) if p95_str is not None else None,
            "basis": basis,
            "gateway_selected_backend": gw or None,
            "gateway_fallback": fallback,
        },
        "answer": answer,
        "synthesis_mode": "template+local_llm" if commentary.get("ok") else "template",
        "llm_commentary": commentary,
        "format_number_example": format_number(1.0),
    }
