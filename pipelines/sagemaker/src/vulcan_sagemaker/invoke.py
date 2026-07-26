"""Invoke a SageMaker real-time endpoint with contract-shaped llm payloads."""

from __future__ import annotations

import json
from typing import Any

import boto3

from vulcan_sagemaker.config import ENDPOINT_NAME
from vulcan_sagemaker.pins import MODEL_ID


def build_infer_request(
    *,
    prompt: str,
    request_id: str = "sagemaker-invoke",
    max_tokens: int = 32,
) -> dict[str, Any]:
    """North-bound shape aligned with ``POST /v1/infer`` modality=llm."""
    return {
        "request_id": request_id,
        "modality": "llm",
        "model_id": MODEL_ID,
        "input": {
            "prompt": prompt,
            "max_tokens": max_tokens,
        },
    }


def invoke_endpoint(
    *,
    payload: dict[str, Any] | None = None,
    prompt: str = "Hello from Vulcan",
    endpoint_name: str = ENDPOINT_NAME,
    region: str = "us-east-1",
    runtime_client: Any = None,
) -> dict[str, Any]:
    """InvokeEndpoint and parse JSON. Maps to contract ``/v1/infer`` vocabulary."""
    body = payload if payload is not None else build_infer_request(prompt=prompt)
    runtime = runtime_client or boto3.client("sagemaker-runtime", region_name=region)
    resp = runtime.invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Accept="application/json",
        Body=json.dumps(body).encode("utf-8"),
    )
    raw = resp["Body"].read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
    else:
        text = str(raw)
    try:
        parsed: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        parsed = {"raw": text}
    return {
        "endpoint_name": endpoint_name,
        "request": body,
        "response": parsed,
        "content_type": resp.get("ContentType", "application/json"),
    }
