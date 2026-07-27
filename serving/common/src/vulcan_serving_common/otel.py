"""Optional OpenTelemetry FastAPI instrumentation for Vulcan adapters.

Enabled when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (e.g. ``http://otel-collector:4318``).
No-ops when the endpoint is unset or OTel packages are missing — keeps CPU images lean
and ADR-002 CI green without a collector.
"""

from __future__ import annotations

import logging
import os
from typing import Any

_LOG = logging.getLogger(__name__)


def instrument_fastapi(app: Any, service_name: str) -> bool:
    """Attach OTLP HTTP tracing to a FastAPI app. Returns True if enabled."""
    endpoint = (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").rstrip("/")
    if not endpoint:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    except ImportError as exc:  # pragma: no cover
        _LOG.warning("OTel packages missing; tracing disabled: %s", exc)
        return False

    ratio = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "1.0"))
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "vulcan",
            "deployment.environment": os.environ.get("VULCAN_ENV", "local"),
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(ratio)),
    )
    # OTLP HTTP trace path is /v1/traces on the collector.
    exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
    _LOG.info("OpenTelemetry enabled for %s → %s", service_name, endpoint)
    return True
