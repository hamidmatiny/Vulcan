"""Tool: PromQL against local Prometheus (ADR-014)."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from advisor.non_fabrication import EvidenceItem, add_backend, add_number


DEFAULT_PROM_URL = "http://127.0.0.1:9008"

# Same cost/latency family as observability/scripts/ci_smoke.sh
COST_QUERY = "vulcan_estimated_cost_usd_per_token"
LATENCY_CATALOG_QUERY = "vulcan_routing_latency_p95_ms"
LIVE_P95_QUERY = (
    "histogram_quantile(0.95, sum by (backend, le) "
    "(rate(vulcan_infer_latency_seconds_bucket[5m])))"
)


def prom_url() -> str:
    return os.environ.get("VULCAN_PROM_URL", DEFAULT_PROM_URL).rstrip("/")


def query_prometheus(
    query: str,
    *,
    base_url: str | None = None,
    evidence: list[EvidenceItem] | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Execute Instant Query; optionally record numeric/backend evidence."""
    root = (base_url or prom_url()).rstrip("/")
    url = f"{root}/api/v1/query?{urllib.parse.urlencode({'query': query})}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise RuntimeError(f"prometheus query failed: {payload}")
    result = payload.get("data", {}).get("result") or []
    series: list[dict[str, Any]] = []
    for row in result:
        metric = row.get("metric") or {}
        value = row.get("value")
        if not value or len(value) < 2:
            continue
        raw = value[1]
        try:
            num = float(raw)
        except (TypeError, ValueError):
            continue
        backend = metric.get("backend") or metric.get("job") or "unknown"
        entry = {
            "backend": backend,
            "metric": dict(metric),
            "value": num,
            "query": query,
        }
        series.append(entry)
        if evidence is not None:
            add_backend(evidence, "query_prometheus", f"backend:{backend}", backend)
            add_number(evidence, "query_prometheus", f"{query}:{backend}", num)
    return {"status": "success", "query": query, "series": series, "count": len(series)}


def fetch_advisor_prometheus(*, evidence: list[EvidenceItem] | None = None) -> dict[str, Any]:
    """Bundle the PromQL queries the advisor uses for cost/latency recommendations."""
    cost = query_prometheus(COST_QUERY, evidence=evidence)
    catalog = query_prometheus(LATENCY_CATALOG_QUERY, evidence=evidence)
    live: dict[str, Any]
    try:
        live = query_prometheus(LIVE_P95_QUERY, evidence=evidence)
    except Exception as exc:  # noqa: BLE001 — live series may be empty early
        live = {"status": "unavailable", "error": str(exc), "series": [], "count": 0}
    return {
        "cost_per_token": cost,
        "catalog_latency_p95_ms": catalog,
        "live_infer_p95_seconds": live,
    }
