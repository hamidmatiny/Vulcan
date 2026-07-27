"""Tool: live gateway routing decision (ADR-014)."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from advisor.non_fabrication import EvidenceItem, add_backend, add_bool, add_number


DEFAULT_GATEWAY_URL = "http://127.0.0.1:9007"

_PAYLOAD = {
    "request_id": "advisor-routing-1",
    "modality": "llm",
    "model_id": "reference-tiny-llm",
    "input": {
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 8,
        "temperature": 0,
    },
}


def gateway_url() -> str:
    return os.environ.get("VULCAN_GATEWAY_URL", DEFAULT_GATEWAY_URL).rstrip("/")


def query_routing_history(
    *,
    base_url: str | None = None,
    evidence: list[EvidenceItem] | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """POST /v1/infer and return the ``routing`` object (same surface as ci_fallback.sh)."""
    root = (base_url or gateway_url()).rstrip("/")
    url = f"{root}/v1/infer"
    body = json.dumps(_PAYLOAD).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    routing = payload.get("routing")
    if not isinstance(routing, dict):
        raise RuntimeError(f"gateway response missing routing object: keys={list(payload)}")

    selected = str(routing.get("selected_backend") or "")
    fallback = bool(routing.get("fallback"))
    if evidence is not None:
        if selected:
            add_backend(evidence, "query_routing_history", "selected_backend", selected)
        add_bool(evidence, "query_routing_history", "fallback", fallback)
        add_backend(evidence, "query_routing_history", "model_id", "reference-tiny-llm")
        for cand in routing.get("candidates") or []:
            if not isinstance(cand, dict):
                continue
            b = cand.get("backend")
            if b:
                add_backend(evidence, "query_routing_history", f"candidate:{b}", str(b))
            if cand.get("latency_p95_ms") is not None:
                add_number(
                    evidence,
                    "query_routing_history",
                    f"candidate_p95:{b}",
                    float(cand["latency_p95_ms"]),
                )
            if cand.get("cost_usd_per_1k_tokens") is not None:
                add_number(
                    evidence,
                    "query_routing_history",
                    f"candidate_cost_1k:{b}",
                    float(cand["cost_usd_per_1k_tokens"]),
                )
        for attempt in routing.get("attempts") or []:
            if not isinstance(attempt, dict):
                continue
            b = attempt.get("backend")
            if b:
                add_backend(evidence, "query_routing_history", f"attempt:{b}", str(b))

    return {
        "gateway_url": root,
        "routing": routing,
        "selected_backend": selected,
        "fallback": fallback,
    }
