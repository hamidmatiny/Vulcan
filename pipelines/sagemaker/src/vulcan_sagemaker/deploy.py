"""Deploy a registered model package to a real-time SageMaker Endpoint."""

from __future__ import annotations

import time
from typing import Any

import boto3

from vulcan_sagemaker.config import BACKEND_ID, DEFAULT_ENDPOINT_INSTANCE, ENDPOINT_NAME
from vulcan_sagemaker.pins import MODEL_ID


def deploy_endpoint(
    *,
    model_package_arn: str,
    role: str,
    endpoint_name: str = ENDPOINT_NAME,
    instance_type: str = DEFAULT_ENDPOINT_INSTANCE,
    initial_instance_count: int = 1,
    region: str = "us-east-1",
    client: Any = None,
    wait: bool = False,
) -> dict[str, str]:
    """Create Model + EndpointConfig + Endpoint from a Model Registry package ARN."""
    sm = client or boto3.client("sagemaker", region_name=region)
    suffix = str(int(time.time()))
    model_name = f"{endpoint_name}-model-{suffix}"
    config_name = f"{endpoint_name}-config-{suffix}"

    sm.create_model(
        ModelName=model_name,
        ExecutionRoleArn=role,
        Containers=[{"ModelPackageName": model_package_arn}],
        Tags=[
            {"Key": "vulcan.dev/model_id", "Value": MODEL_ID},
            {"Key": "vulcan.dev/backend", "Value": BACKEND_ID},
        ],
    )

    sm.create_endpoint_config(
        EndpointConfigName=config_name,
        ProductionVariants=[
            {
                "VariantName": "AllTraffic",
                "ModelName": model_name,
                "InitialInstanceCount": initial_instance_count,
                "InstanceType": instance_type,
                "InitialVariantWeight": 1.0,
            }
        ],
        Tags=[
            {"Key": "vulcan.dev/model_id", "Value": MODEL_ID},
            {"Key": "vulcan.dev/backend", "Value": BACKEND_ID},
        ],
    )

    sm.create_endpoint(
        EndpointName=endpoint_name,
        EndpointConfigName=config_name,
        Tags=[
            {"Key": "vulcan.dev/model_id", "Value": MODEL_ID},
            {"Key": "vulcan.dev/backend", "Value": BACKEND_ID},
        ],
    )

    if wait:
        waiter = sm.get_waiter("endpoint_in_service")
        waiter.wait(EndpointName=endpoint_name)

    return {
        "endpoint_name": endpoint_name,
        "model_name": model_name,
        "endpoint_config_name": config_name,
        "model_package_arn": model_package_arn,
    }
