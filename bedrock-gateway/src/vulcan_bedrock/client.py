"""Bedrock Runtime client — maps Vulcan LLM messages ↔ InvokeModel payloads."""

from __future__ import annotations

import json
from typing import Any

import boto3
from botocore.response import StreamingBody


DEFAULT_MODEL_ID = "amazon.titan-text-express-v1"


def messages_to_prompt(messages: list[dict[str, str]]) -> str:
    """Flatten contract chat messages into a single prompt string."""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def build_invoke_body(
    *,
    model_id: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
) -> tuple[bytes, str]:
    """Return (body_bytes, content_type) for bedrock-runtime invoke_model."""
    prompt = messages_to_prompt(messages)
    mid = model_id.lower()
    if mid.startswith("amazon.titan"):
        payload = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": max_tokens,
                "temperature": min(max(temperature, 0.0), 1.0),
            },
        }
        return json.dumps(payload).encode("utf-8"), "application/json"
    if mid.startswith("anthropic.claude"):
        # Legacy Claude text completion shape still widely used with InvokeModel.
        payload = {
            "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
            "max_tokens_to_sample": max_tokens,
            "temperature": temperature,
        }
        return json.dumps(payload).encode("utf-8"), "application/json"
    # Generic JSON fallback for other foundation models.
    payload = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    return json.dumps(payload).encode("utf-8"), "application/json"


def parse_invoke_response(model_id: str, body: bytes | str | StreamingBody) -> dict[str, Any]:
    """Normalize Bedrock provider JSON into Vulcan LlmOutput fields (+ usage)."""
    if hasattr(body, "read"):
        raw = body.read()  # type: ignore[union-attr]
    else:
        raw = body
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
    else:
        text = str(raw)
    data = json.loads(text) if text else {}

    mid = model_id.lower()
    completion = ""
    if mid.startswith("amazon.titan"):
        completion = str(data.get("results", [{}])[0].get("outputText", "") or "")
        inp = int(data.get("inputTextTokenCount") or 0)
        out = int((data.get("results") or [{}])[0].get("tokenCount") or 0)
    elif mid.startswith("anthropic.claude"):
        completion = str(data.get("completion") or data.get("content", "") or "")
        if isinstance(data.get("content"), list):
            chunks = [
                c.get("text", "")
                for c in data["content"]
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            completion = "".join(chunks) or completion
        usage = data.get("usage") or {}
        inp = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    else:
        completion = str(
            data.get("generation")
            or data.get("completion")
            or data.get("outputText")
            or data.get("text")
            or ""
        )
        usage = data.get("usage") or {}
        inp = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)

    return {
        "text": completion,
        "finish_reason": "stop",
        "usage": {
            "prompt_tokens": inp,
            "completion_tokens": out,
            "total_tokens": inp + out,
        },
    }


class BedrockClient:
    """Thin wrapper around bedrock-runtime; injectable for tests."""

    def __init__(
        self,
        *,
        region: str = "us-east-1",
        client: Any = None,
    ) -> None:
        self.region = region
        self._client = client or boto3.client("bedrock-runtime", region_name=region)

    def infer_llm(
        self,
        *,
        model_id: str,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        body, content_type = build_invoke_body(
            model_id=model_id,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        resp = self._client.invoke_model(
            modelId=model_id,
            body=body,
            contentType=content_type,
            accept="application/json",
        )
        return parse_invoke_response(model_id, resp["body"])
