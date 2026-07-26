"""moto-backed AWS fixtures — no live network or credentials."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws


@pytest.fixture()
def aws_region() -> str:
    return "us-east-1"


@pytest.fixture()
def aws(aws_region: str):
    with mock_aws():
        # Force fake credentials so nothing accidentally hits a real account.
        session = boto3.Session(
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            aws_session_token="testing",
            region_name=aws_region,
        )
        yield session


@pytest.fixture()
def role_arn(aws, aws_region: str) -> str:
    iam = aws.client("iam", region_name=aws_region)
    resp = iam.create_role(
        RoleName="VulcanSageMakerRole",
        AssumeRolePolicyDocument=(
            '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",'
            '"Principal":{"Service":"sagemaker.amazonaws.com"},'
            '"Action":"sts:AssumeRole"}]}'
        ),
    )
    return str(resp["Role"]["Arn"])


@pytest.fixture()
def bucket_name(aws, aws_region: str) -> str:
    s3 = aws.client("s3", region_name=aws_region)
    name = "vulcan-sagemaker-test"
    s3.create_bucket(Bucket=name)
    return name
