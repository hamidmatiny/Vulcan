"""Unit tests for VulcanClient against the reference server fixture."""

from __future__ import annotations

from vulcan_serving_common.client import VulcanClient


def test_client_context_manager(backend_url: str) -> None:
    with VulcanClient(backend_url) as client:
        assert client.health()["status"] == "ok"
