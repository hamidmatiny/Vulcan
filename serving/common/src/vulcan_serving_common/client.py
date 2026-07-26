"""Thin HTTP client for any Vulcan model-contract backend."""

from __future__ import annotations

from typing import Any, Self

import httpx


class VulcanClientError(RuntimeError):
    """Raised when a backend returns a non-success response or invalid payload."""

    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class VulcanClient:
    """Uniform client for `/health`, `/metrics`, `/v1/infer`, `/v1/resources`."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        return self._get_json("/health")

    def metrics(self) -> str:
        resp = self._client.get("/metrics")
        if resp.status_code != 200:
            raise VulcanClientError(
                f"GET /metrics failed: {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text,
            )
        return resp.text

    def resources(self) -> dict[str, Any]:
        return self._get_json("/v1/resources")

    def infer(self, request: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.post("/v1/infer", json=request)
        if resp.status_code != 200:
            try:
                body: Any = resp.json()
            except Exception:  # noqa: BLE001 — surface raw body
                body = resp.text
            raise VulcanClientError(
                f"POST /v1/infer failed: {resp.status_code}",
                status_code=resp.status_code,
                body=body,
            )
        data = resp.json()
        if not isinstance(data, dict):
            raise VulcanClientError("infer response must be a JSON object", body=data)
        return data

    def infer_llm(
        self,
        *,
        model_id: str,
        messages: list[dict[str, str]],
        request_id: str = "client-llm",
        max_tokens: int = 16,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        return self.infer(
            {
                "request_id": request_id,
                "modality": "llm",
                "model_id": model_id,
                "input": {
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            }
        )

    def infer_vision(
        self,
        *,
        model_id: str,
        images: list[dict[str, str]],
        request_id: str = "client-vision",
        prompt: str | None = None,
        max_tokens: int = 32,
    ) -> dict[str, Any]:
        payload_input: dict[str, Any] = {"images": images, "max_tokens": max_tokens}
        if prompt is not None:
            payload_input["prompt"] = prompt
        return self.infer(
            {
                "request_id": request_id,
                "modality": "vision",
                "model_id": model_id,
                "input": payload_input,
            }
        )

    def _get_json(self, path: str) -> dict[str, Any]:
        resp = self._client.get(path)
        if resp.status_code != 200:
            raise VulcanClientError(
                f"GET {path} failed: {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text,
            )
        data = resp.json()
        if not isinstance(data, dict):
            raise VulcanClientError(f"{path} response must be a JSON object", body=data)
        return data
