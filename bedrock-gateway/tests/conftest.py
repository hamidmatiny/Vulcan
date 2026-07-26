"""moto + fake credentials — same spirit as phase-10 SageMaker CI (no live AWS)."""

from __future__ import annotations

import io
import json
from typing import Any

import boto3
import pytest
from moto import mock_aws

from vulcan_bedrock.client import BedrockClient
from vulcan_bedrock.service import app, set_client


@pytest.fixture()
def aws_region() -> str:
    return "us-east-1"


@pytest.fixture()
def aws(aws_region: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", aws_region)
    with mock_aws():
        yield boto3.Session(
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            aws_session_token="testing",
            region_name=aws_region,
        )


def _fake_invoke_model(**kwargs: Any) -> dict[str, Any]:
    model_id = kwargs.get("modelId", "")
    if str(model_id).startswith("amazon.titan"):
        payload = {
            "inputTextTokenCount": 5,
            "results": [{"outputText": "hello from titan", "tokenCount": 3}],
        }
    elif str(model_id).startswith("anthropic.claude"):
        payload = {
            "completion": "hello from claude",
            "usage": {"input_tokens": 4, "output_tokens": 3},
        }
    else:
        payload = {"generation": "hello generic", "usage": {"input_tokens": 2, "output_tokens": 2}}
    return {
        "body": io.BytesIO(json.dumps(payload).encode("utf-8")),
        "contentType": "application/json",
    }


@pytest.fixture()
def bedrock_client(aws, aws_region: str, monkeypatch: pytest.MonkeyPatch) -> BedrockClient:
    """BedrockClient whose invoke_model is stubbed (moto coverage of Bedrock varies)."""
    runtime = aws.client("bedrock-runtime", region_name=aws_region)
    monkeypatch.setattr(runtime, "invoke_model", _fake_invoke_model)
    return BedrockClient(region=aws_region, client=runtime)


@pytest.fixture()
def api_client(bedrock_client: BedrockClient):
    from fastapi.testclient import TestClient

    set_client(bedrock_client)
    with TestClient(app) as client:
        yield client
    set_client(None)
