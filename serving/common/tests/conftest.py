"""Start the trivial reference server for conformance tests when no URL is set."""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Iterator

import pytest

from vulcan_serving_common.client import VulcanClient
from vulcan_serving_common.reference_server import create_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Optional modality filter for LLM-only backends (e.g. vLLM).

    Set ``VULCAN_CONFORMANCE_MODALITIES=llm`` to skip vision *success* tests.
    Does not alter test bodies — suite modules stay shared across backends.
    """
    raw = os.environ.get("VULCAN_CONFORMANCE_MODALITIES", "llm,vision")
    allowed = {part.strip().lower() for part in raw.split(",") if part.strip()}
    if "vision" in allowed:
        return
    skip_vision = pytest.mark.skip(
        reason="VULCAN_CONFORMANCE_MODALITIES excludes vision (LLM-only backend)"
    )
    for item in items:
        if item.name == "test_infer_vision_schema":
            item.add_marker(skip_vision)


@pytest.fixture(scope="session")
def backend_url() -> Iterator[str]:
    """Point conformance at VULCAN_BACKEND_URL or a local reference server."""
    existing = os.environ.get("VULCAN_BACKEND_URL")
    if existing:
        yield existing.rstrip("/")
        return

    port = _free_port()
    server = create_server("127.0.0.1", port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    # Wait until /health responds.
    deadline = time.time() + 5
    with VulcanClient(url, timeout=1.0) as client:
        while time.time() < deadline:
            try:
                client.health()
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        else:
            server.shutdown()
            raise RuntimeError("reference server failed to start")
    try:
        yield url
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.fixture
def client(backend_url: str) -> Iterator[VulcanClient]:
    with VulcanClient(backend_url) as c:
        yield c
