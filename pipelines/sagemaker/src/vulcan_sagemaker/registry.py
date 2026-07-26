"""SageMaker Model Registry helpers (create group + register package version)."""

from __future__ import annotations

import json
from typing import Any

import boto3
from botocore.exceptions import ClientError

from vulcan_sagemaker.config import BACKEND_ID, MODEL_PACKAGE_GROUP
from vulcan_sagemaker.pins import MODEL_ID, load_reference_llm_pin


def ensure_model_package_group(
    *,
    group_name: str = MODEL_PACKAGE_GROUP,
    region: str = "us-east-1",
    client: Any = None,
) -> str:
    sm = client or boto3.client("sagemaker", region_name=region)
    pin = load_reference_llm_pin()
    try:
        sm.create_model_package_group(
            ModelPackageGroupName=group_name,
            ModelPackageGroupDescription=(
                f"Vulcan {MODEL_ID} — {pin.repo_id}@{pin.revision} "
                f"(backend={BACKEND_ID})"
            ),
            Tags=[
                {"Key": "vulcan.dev/model_id", "Value": MODEL_ID},
                {"Key": "vulcan.dev/backend", "Value": BACKEND_ID},
            ],
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        msg = str(exc).lower()
        if code in {"ValidationException", "ResourceInUse", "ResourceAlreadyExists"}:
            return group_name
        if "already exist" in msg or "cannot create" in msg:
            return group_name
        raise
    return group_name


def register_model_package(
    *,
    model_data_url: str,
    image_uri: str,
    evaluation: dict[str, Any],
    group_name: str = MODEL_PACKAGE_GROUP,
    approval_status: str = "PendingManualApproval",
    region: str = "us-east-1",
    client: Any = None,
) -> str:
    """Register a model package version with eval_loss / perplexity metadata."""
    sm = client or boto3.client("sagemaker", region_name=region)
    pin = load_reference_llm_pin()
    ensure_model_package_group(group_name=group_name, region=region, client=sm)

    # CustomerMetadataProperties values must be strings.
    metadata = {
        "model_id": MODEL_ID,
        "hub_repo_id": pin.repo_id,
        "revision": pin.revision,
        "eval_loss": str(evaluation["eval_loss"]),
        "perplexity": str(evaluation["perplexity"]),
        "backend": BACKEND_ID,
        "evaluation_json": json.dumps(
            {
                "eval_loss": evaluation["eval_loss"],
                "perplexity": evaluation["perplexity"],
            },
            sort_keys=True,
        ),
    }

    resp = sm.create_model_package(
        ModelPackageGroupName=group_name,
        ModelPackageDescription=f"Vulcan {MODEL_ID} eval_loss={evaluation['eval_loss']}",
        ModelApprovalStatus=approval_status,
        InferenceSpecification={
            "Containers": [
                {
                    "Image": image_uri,
                    "ModelDataUrl": model_data_url,
                    "Environment": {
                        "VULCAN_MODEL_ID": MODEL_ID,
                        "VULCAN_HF_REVISION": pin.revision,
                    },
                }
            ],
            "SupportedContentTypes": ["application/json"],
            "SupportedResponseMIMETypes": ["application/json"],
            "SupportedRealtimeInferenceInstanceTypes": ["ml.m5.large", "ml.m5.xlarge"],
            "SupportedTransformInstanceTypes": ["ml.m5.large"],
        },
        CustomerMetadataProperties=metadata,
    )
    return str(resp["ModelPackageArn"])
