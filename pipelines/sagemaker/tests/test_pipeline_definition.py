"""Pipeline definition via SageMaker SDK — moto session, no live AWS."""

from __future__ import annotations

from sagemaker.workflow.pipeline_context import PipelineSession

from vulcan_sagemaker.config import MODEL_PACKAGE_GROUP, PIPELINE_NAME
from vulcan_sagemaker.pipeline import (
    build_pipeline,
    pipeline_definition_dict,
    step_names,
    upsert_pipeline,
)
from vulcan_sagemaker.pins import MODEL_ID


def test_pipeline_definition_contains_train_eval_register(
    aws, role_arn: str, bucket_name: str, aws_region: str
) -> None:
    session = PipelineSession(boto_session=aws)
    definition = pipeline_definition_dict(
        role=role_arn,
        bucket=bucket_name,
        region=aws_region,
        sagemaker_session=session,
    )
    names = step_names(definition)
    joined = " ".join(names)
    assert "TrainReferenceTinyLlm" in joined
    assert "EvaluateReferenceTinyLlm" in joined
    # RegisterModel may appear as RegisterReferenceTinyLlm or nested register steps.
    assert "Register" in joined or MODEL_PACKAGE_GROUP in str(definition)

    raw = str(definition)
    assert MODEL_ID in raw or "reference-tiny-llm" in raw
    assert "eval" in raw.lower() or "Evaluate" in joined


def test_upsert_pipeline_with_moto(
    aws, role_arn: str, bucket_name: str, aws_region: str
) -> None:
    session = PipelineSession(boto_session=aws)
    name = upsert_pipeline(
        role=role_arn,
        bucket=bucket_name,
        region=aws_region,
        sagemaker_session=session,
    )
    assert name == PIPELINE_NAME
    sm = aws.client("sagemaker", region_name=aws_region)
    desc = sm.describe_pipeline(PipelineName=name)
    assert desc["PipelineName"] == PIPELINE_NAME


def test_build_pipeline_parameters(aws, role_arn: str, bucket_name: str) -> None:
    session = PipelineSession(boto_session=aws)
    pipe = build_pipeline(
        role=role_arn,
        bucket=bucket_name,
        sagemaker_session=session,
    )
    param_names = {p.name for p in pipe.parameters}
    assert "ModelApprovalStatus" in param_names
    assert "TrainInstanceType" in param_names
    assert "TrainSteps" in param_names
