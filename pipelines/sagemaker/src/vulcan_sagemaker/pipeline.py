"""SageMaker Pipelines definition for train → evaluate → register.

Uses the SageMaker Python SDK. CI never upserts or starts executions against a
live account — tests build the definition JSON and exercise registry/deploy via moto.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sagemaker.estimator import Estimator
from sagemaker.inputs import TrainingInput
from sagemaker.model_metrics import MetricsSource, ModelMetrics
from sagemaker.processing import ProcessingInput, ProcessingOutput, ScriptProcessor
from sagemaker.workflow.parameters import ParameterInteger, ParameterString
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.properties import PropertyFile
from sagemaker.workflow.step_collections import RegisterModel
from sagemaker.workflow.steps import ProcessingStep, TrainingStep

from vulcan_sagemaker.config import (
    BACKEND_ID,
    DEFAULT_TRAIN_INSTANCE,
    DEFAULT_TRANSFORM_INSTANCE,
    MODEL_PACKAGE_GROUP,
    PIPELINE_NAME,
)
from vulcan_sagemaker.pins import MODEL_ID, load_reference_llm_pin

# Public CPU sklearn image is enough to *define* the graph; manual runs may
# swap instance types / images via parameters (see runbook).
_DEFAULT_SKLEARN_IMAGE = (
    "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3"
)


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent


def build_pipeline(
    *,
    role: str,
    bucket: str,
    pipeline_name: str = PIPELINE_NAME,
    region: str = "us-east-1",
    sagemaker_session: Any = None,
    image_uri: str | None = None,
) -> Pipeline:
    """Construct the train → evaluate → register Pipeline (does not start it)."""
    pin = load_reference_llm_pin()
    image = image_uri or _DEFAULT_SKLEARN_IMAGE
    eval_metrics_uri = f"s3://{bucket}/vulcan/{MODEL_ID}/evaluation/evaluation_report.json"

    model_approval = ParameterString(
        name="ModelApprovalStatus",
        default_value="PendingManualApproval",
    )
    train_instance = ParameterString(
        name="TrainInstanceType",
        default_value=DEFAULT_TRAIN_INSTANCE,
    )
    train_steps = ParameterInteger(name="TrainSteps", default_value=20)
    input_data = ParameterString(
        name="TrainDataUri",
        default_value=f"s3://{bucket}/vulcan/{MODEL_ID}/train/",
    )

    estimator = Estimator(
        image_uri=image,
        role=role,
        instance_count=1,
        instance_type=train_instance,
        output_path=f"s3://{bucket}/vulcan/{MODEL_ID}/model/",
        sagemaker_session=sagemaker_session,
        entry_point="train.py",
        source_dir=str(_scripts_dir()),
        hyperparameters={"total-steps": train_steps},
        environment={
            "VULCAN_MODEL_ID": MODEL_ID,
            "VULCAN_HF_REVISION": pin.revision,
            "VULCAN_BACKEND": BACKEND_ID,
        },
        base_job_name="vulcan-ref-llm-train",
    )

    train_step = TrainingStep(
        name="TrainReferenceTinyLlm",
        estimator=estimator,
        inputs={
            "train": TrainingInput(s3_data=input_data, content_type="text/plain"),
        },
    )

    eval_processor = ScriptProcessor(
        image_uri=image,
        command=["python3"],
        role=role,
        instance_count=1,
        instance_type=DEFAULT_TRANSFORM_INSTANCE,
        sagemaker_session=sagemaker_session,
        base_job_name="vulcan-ref-llm-eval",
        env={
            "VULCAN_MODEL_ID": MODEL_ID,
            "VULCAN_HF_REVISION": pin.revision,
        },
    )

    evaluation_report = PropertyFile(
        name="EvaluationReport",
        output_name="evaluation",
        path="evaluation_report.json",
    )

    eval_step = ProcessingStep(
        name="EvaluateReferenceTinyLlm",
        processor=eval_processor,
        inputs=[
            ProcessingInput(
                source=train_step.properties.ModelArtifacts.S3ModelArtifacts,
                destination="/opt/ml/processing/model",
            )
        ],
        outputs=[
            ProcessingOutput(
                output_name="evaluation",
                source="/opt/ml/processing/evaluation",
                destination=f"s3://{bucket}/vulcan/{MODEL_ID}/evaluation",
            ),
        ],
        code=str(_scripts_dir() / "evaluate.py"),
        property_files=[evaluation_report],
    )

    model_metrics = ModelMetrics(
        model_statistics=MetricsSource(
            s3_uri=eval_metrics_uri,
            content_type="application/json",
        )
    )

    register_step = RegisterModel(
        name="RegisterReferenceTinyLlm",
        estimator=estimator,
        model_data=train_step.properties.ModelArtifacts.S3ModelArtifacts,
        content_types=["application/json"],
        response_types=["application/json"],
        inference_instances=[DEFAULT_TRANSFORM_INSTANCE, "ml.m5.xlarge"],
        transform_instances=[DEFAULT_TRANSFORM_INSTANCE],
        model_package_group_name=MODEL_PACKAGE_GROUP,
        approval_status=model_approval,
        model_metrics=model_metrics,
        description=f"Vulcan {MODEL_ID} ({pin.repo_id}@{pin.revision[:12]})",
        depends_on=[eval_step],
    )

    return Pipeline(
        name=pipeline_name,
        parameters=[model_approval, train_instance, train_steps, input_data],
        steps=[train_step, eval_step, register_step],
        sagemaker_session=sagemaker_session,
    )


def pipeline_definition_dict(
    *,
    role: str,
    bucket: str,
    region: str = "us-east-1",
    sagemaker_session: Any = None,
) -> dict[str, Any]:
    """Return the JSON-serializable pipeline definition (no AWS side effects)."""
    pipe = build_pipeline(
        role=role,
        bucket=bucket,
        region=region,
        sagemaker_session=sagemaker_session,
    )
    return json.loads(pipe.definition())


def upsert_pipeline(
    *,
    role: str,
    bucket: str,
    region: str = "us-east-1",
    sagemaker_session: Any = None,
) -> str:
    """Create/update the pipeline in the bound session (moto or real AWS)."""
    pipe = build_pipeline(
        role=role,
        bucket=bucket,
        region=region,
        sagemaker_session=sagemaker_session,
    )
    pipe.upsert(role_arn=role)
    return pipe.name


def step_names(definition: dict[str, Any]) -> list[str]:
    """Extract step names from a pipeline definition dict."""
    steps = definition.get("Steps") or definition.get("steps") or []
    names: list[str] = []
    for step in steps:
        name = step.get("Name") or step.get("name")
        if name:
            names.append(str(name))
        # RegisterModel expands into nested steps in some SDK versions.
        for nested in step.get("Steps") or step.get("steps") or []:
            nested_name = nested.get("Name") or nested.get("name")
            if nested_name:
                names.append(str(nested_name))
    return names
