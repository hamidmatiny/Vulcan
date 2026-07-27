"""LangGraph wiring for the Vulcan advisor (ADR-014)."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from advisor.non_fabrication import EvidenceItem, assert_answer_grounded
from advisor.recommend import synthesize_recommendation
from advisor.tools_benchmarks import read_benchmark_results
from advisor.tools_prometheus import fetch_advisor_prometheus
from advisor.tools_routing import query_routing_history


class AdvisorState(TypedDict, total=False):
    question: str
    evidence: list[dict[str, Any]]
    prometheus: dict[str, Any]
    benchmarks: dict[str, Any]
    routing: dict[str, Any]
    recommendation: dict[str, Any]
    answer: str
    synthesis_mode: str
    llm_commentary: dict[str, Any]
    use_local_llm: bool


def _evidence_from_state(state: AdvisorState) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for raw in state.get("evidence") or []:
        items.append(
            EvidenceItem(
                tool=str(raw["tool"]),
                kind=str(raw["kind"]),
                key=str(raw["key"]),
                value=raw["value"],
                value_str=str(raw["value_str"]),
            )
        )
    return items


def _evidence_to_state(items: list[EvidenceItem]) -> list[dict[str, Any]]:
    return [e.to_dict() for e in items]


def node_query_prometheus(state: AdvisorState) -> dict[str, Any]:
    evidence = _evidence_from_state(state)
    prom = fetch_advisor_prometheus(evidence=evidence)
    return {"prometheus": prom, "evidence": _evidence_to_state(evidence)}


def node_read_benchmarks(state: AdvisorState) -> dict[str, Any]:
    evidence = _evidence_from_state(state)
    benches = read_benchmark_results(evidence=evidence)
    return {"benchmarks": benches, "evidence": _evidence_to_state(evidence)}


def node_query_routing(state: AdvisorState) -> dict[str, Any]:
    evidence = _evidence_from_state(state)
    routing = query_routing_history(evidence=evidence)
    return {"routing": routing, "evidence": _evidence_to_state(evidence)}


def node_recommend(state: AdvisorState) -> dict[str, Any]:
    evidence = _evidence_from_state(state)
    out = synthesize_recommendation(
        question=str(state.get("question") or ""),
        prometheus=state.get("prometheus") or {},
        benchmarks=state.get("benchmarks") or {},
        routing=state.get("routing") or {},
        evidence=evidence,
        use_local_llm=bool(state.get("use_local_llm", True)),
    )
    assert_answer_grounded(out["answer"], evidence)
    return {
        "recommendation": out["recommendation"],
        "answer": out["answer"],
        "synthesis_mode": out["synthesis_mode"],
        "llm_commentary": out["llm_commentary"],
        "evidence": _evidence_to_state(evidence),
    }


def build_graph():
    g: StateGraph = StateGraph(AdvisorState)
    g.add_node("query_prometheus", node_query_prometheus)
    g.add_node("read_benchmark_results", node_read_benchmarks)
    g.add_node("query_routing_history", node_query_routing)
    g.add_node("recommend", node_recommend)
    g.add_edge(START, "query_prometheus")
    g.add_edge("query_prometheus", "read_benchmark_results")
    g.add_edge("read_benchmark_results", "query_routing_history")
    g.add_edge("query_routing_history", "recommend")
    g.add_edge("recommend", END)
    return g.compile()


def run_advisor(
    question: str,
    *,
    use_local_llm: bool = True,
) -> dict[str, Any]:
    """Run the full tool-grounded graph and return the final state."""
    app = build_graph()
    final = app.invoke(
        {
            "question": question,
            "evidence": [],
            "use_local_llm": use_local_llm,
        }
    )
    evidence = _evidence_from_state(final)
    assert_answer_grounded(str(final.get("answer") or ""), evidence)
    return dict(final)
