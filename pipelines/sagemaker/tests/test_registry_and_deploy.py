"""Model Registry + Endpoint create via moto."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from vulcan_sagemaker.deploy import deploy_endpoint
from vulcan_sagemaker.evaluate import run_evaluation
from vulcan_sagemaker.invoke import build_infer_request, invoke_endpoint
from vulcan_sagemaker.registry import ensure_model_package_group, register_model_package
from vulcan_sagemaker.train import run_training


_IMAGE = (
    "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3"
)


def test_register_and_deploy_endpoint(
    aws, role_arn: str, bucket_name: str, aws_region: str, tmp_path: Path
) -> None:
    run_training(output_dir=tmp_path / "model", total_steps=15)
    evaluation = run_evaluation(model_dir=tmp_path / "model", output_dir=tmp_path / "eval")

    s3 = aws.client("s3", region_name=aws_region)
    model_key = "vulcan/reference-tiny-llm/model/model.tar.gz"
    s3.put_object(Bucket=bucket_name, Key=model_key, Body=b"fake-weights")
    model_url = f"s3://{bucket_name}/{model_key}"

    sm = aws.client("sagemaker", region_name=aws_region)
    group = ensure_model_package_group(region=aws_region, client=sm)
    arn = register_model_package(
        model_data_url=model_url,
        image_uri=_IMAGE,
        evaluation=evaluation,
        approval_status="Approved",
        region=aws_region,
        client=sm,
    )
    assert group in arn or "model-package" in arn.lower() or arn.startswith("arn:")

    # Second register should reuse the group.
    arn2 = register_model_package(
        model_data_url=model_url,
        image_uri=_IMAGE,
        evaluation=evaluation,
        approval_status="Approved",
        region=aws_region,
        client=sm,
    )
    assert arn2.startswith("arn:")

    deployed = deploy_endpoint(
        model_package_arn=arn,
        role=role_arn,
        endpoint_name="vulcan-test-endpoint",
        region=aws_region,
        client=sm,
        wait=False,
    )
    assert deployed["endpoint_name"] == "vulcan-test-endpoint"
    desc = sm.describe_endpoint(EndpointName="vulcan-test-endpoint")
    assert desc["EndpointName"] == "vulcan-test-endpoint"


def test_build_infer_request_contract_shape() -> None:
    req = build_infer_request(prompt="hi", request_id="t1")
    assert req["modality"] == "llm"
    assert req["model_id"] == "reference-tiny-llm"
    assert req["input"]["prompt"] == "hi"


def test_invoke_endpoint_parses_json() -> None:
    runtime = MagicMock()
    body = MagicMock()
    body.read.return_value = b'{"output":{"text":"ok"}}'
    runtime.invoke_endpoint.return_value = {
        "Body": body,
        "ContentType": "application/json",
    }
    result = invoke_endpoint(
        prompt="hi",
        endpoint_name="ep",
        runtime_client=runtime,
    )
    assert result["response"]["output"]["text"] == "ok"
    runtime.invoke_endpoint.assert_called_once()
    kwargs = runtime.invoke_endpoint.call_args.kwargs
    assert kwargs["EndpointName"] == "ep"
    assert b"reference-tiny-llm" in kwargs["Body"]
