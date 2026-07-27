#!/usr/bin/env python3
"""Synthetic DCGM-shaped metrics for CPU compose / CI (ADR-002).

Emits the same metric *names* operators expect from NVIDIA DCGM Exporter so Grafana
panels can be wired once. Values are SAMPLE data labeled data_source=synthetic_cpu_compose.
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest

REGISTRY = CollectorRegistry()

# Canonical DCGM Exporter names (subset used by Vulcan dashboards).
GPU_UTIL = Gauge(
    "DCGM_FI_DEV_GPU_UTIL",
    "GPU utilization % (0-100). SYNTHETIC in CPU compose — not real DCGM.",
    ["gpu", "UUID", "device", "data_source"],
    registry=REGISTRY,
)
MEM_COPY = Gauge(
    "DCGM_FI_DEV_MEM_COPY_UTIL",
    "Memory copy utilization % (0-100). SYNTHETIC in CPU compose.",
    ["gpu", "UUID", "device", "data_source"],
    registry=REGISTRY,
)
FB_USED = Gauge(
    "DCGM_FI_DEV_FB_USED",
    "Framebuffer used (MiB). SYNTHETIC in CPU compose.",
    ["gpu", "UUID", "device", "data_source"],
    registry=REGISTRY,
)
FB_FREE = Gauge(
    "DCGM_FI_DEV_FB_FREE",
    "Framebuffer free (MiB). SYNTHETIC in CPU compose.",
    ["gpu", "UUID", "device", "data_source"],
    registry=REGISTRY,
)
SYNTH_INFO = Gauge(
    "vulcan_synthetic_dcgm_info",
    "Always 1 when synthetic DCGM exporter is serving sample series",
    ["data_source"],
    registry=REGISTRY,
)

_DATA_SOURCE = "synthetic_cpu_compose"
_UUID = "SYNTHETIC-CPU-COMPOSE-GPU0"
_DEVICE = "synthetic-gpu0"


def refresh() -> None:
    # Stable sample values so CI assertions are deterministic.
    GPU_UTIL.labels("0", _UUID, _DEVICE, _DATA_SOURCE).set(42.0)
    MEM_COPY.labels("0", _UUID, _DEVICE, _DATA_SOURCE).set(11.0)
    FB_USED.labels("0", _UUID, _DEVICE, _DATA_SOURCE).set(2048.0)
    FB_FREE.labels("0", _UUID, _DEVICE, _DATA_SOURCE).set(14336.0)
    SYNTH_INFO.labels(_DATA_SOURCE).set(1)


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
    port = int(os.environ.get("PORT", "9400"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"vulcan synthetic-dcgm on :{port} (data_source={_DATA_SOURCE})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
