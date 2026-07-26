"""CLI entry points for manual AWS runs (never used by CI against live accounts)."""

from __future__ import annotations

import argparse
import json
import os
import sys

import boto3
from sagemaker.workflow.pipeline_context import PipelineSession

from vulcan_sagemaker.config import ENDPOINT_NAME, estimate_manual_smoke_cost
from vulcan_sagemaker.deploy import deploy_endpoint
from vulcan_sagemaker.invoke import invoke_endpoint
from vulcan_sagemaker.pipeline import upsert_pipeline


def _require_explicit_aws() -> None:
    if os.environ.get("VULCAN_ALLOW_LIVE_AWS", "") != "1":
        print(
            "Refusing to call live AWS. Set VULCAN_ALLOW_LIVE_AWS=1 after reading "
            "docs/runbooks/sagemaker-manual-run.md",
            file=sys.stderr,
        )
        raise SystemExit(2)


def upsert_pipeline_main(argv: list[str] | None = None) -> int:
    _require_explicit_aws()
    parser = argparse.ArgumentParser(description="Upsert Vulcan SageMaker Pipeline")
    parser.add_argument("--role", required=True, help="SageMaker execution role ARN")
    parser.add_argument("--bucket", required=True, help="S3 bucket for artifacts")
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    args = parser.parse_args(argv)

    boto_sess = boto3.Session(region_name=args.region)
    sm_sess = PipelineSession(boto_session=boto_sess)
    name = upsert_pipeline(
        role=args.role,
        bucket=args.bucket,
        region=args.region,
        sagemaker_session=sm_sess,
    )
    cost = estimate_manual_smoke_cost(use_gpu=False)
    print(json.dumps({"pipeline": name, "approx_smoke_usd": cost.total_usd}, indent=2))
    return 0


def deploy_main(argv: list[str] | None = None) -> int:
    _require_explicit_aws()
    parser = argparse.ArgumentParser(description="Deploy Model Package to Endpoint")
    parser.add_argument("--role", required=True)
    parser.add_argument("--model-package-arn", required=True)
    parser.add_argument("--endpoint-name", default=ENDPOINT_NAME)
    parser.add_argument("--instance-type", default="ml.m5.large")
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args(argv)

    result = deploy_endpoint(
        model_package_arn=args.model_package_arn,
        role=args.role,
        endpoint_name=args.endpoint_name,
        instance_type=args.instance_type,
        region=args.region,
        wait=args.wait,
    )
    print(json.dumps(result, indent=2))
    return 0


def invoke_main(argv: list[str] | None = None) -> int:
    _require_explicit_aws()
    parser = argparse.ArgumentParser(description="Invoke Vulcan SageMaker Endpoint")
    parser.add_argument("--endpoint-name", default=ENDPOINT_NAME)
    parser.add_argument("--prompt", default="Hello from Vulcan")
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    args = parser.parse_args(argv)
    result = invoke_endpoint(
        prompt=args.prompt,
        endpoint_name=args.endpoint_name,
        region=args.region,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    print("Use vulcan-sm-upsert-pipeline | vulcan-sm-deploy | vulcan-sm-invoke", file=sys.stderr)
    raise SystemExit(2)
