# Runbook: Vulcan SageMaker Pipeline + Endpoint (live AWS)

**Manual only.** CI never uses real AWS credentials or network calls against your account ([ADR-002](../adr/002-gpu-cost-safety-policy.md)). All automation under `pipelines/sagemaker/` is exercised with **moto** mocks.

This runbook trains/evaluates/registers the phase-1 pin **`reference-tiny-llm`** (GPT-2 small @ `models/pins.json` revision) and optionally deploys a real-time Endpoint.

## Prerequisites

1. AWS account + credentials (`aws configure` or env vars) with permissions for SageMaker, S3, IAM pass-role, ECR pull of the training image.
2. An **execution role** ARN SageMaker can assume (`AmazonSageMakerFullAccess` or tighter custom policy).
3. An **S3 bucket** for train data + model artifacts.
4. Local Python 3.11+ and this repo checked out.

```bash
cd pipelines/sagemaker
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

## Expected cost (order of magnitude)

Prices change — verify [SageMaker pricing](https://aws.amazon.com/sagemaker/pricing/) for your region. Ballpark for a **single smoke** in `us-east-1`:

| Path | Train (~15–30 min) | Endpoint (~30–60 min left up) | Rough total |
|------|--------------------|-------------------------------|-------------|
| **CPU** (`ml.m5.xlarge` train, `ml.m5.large` endpoint) | ~$0.05–$0.15 | ~$0.05–$0.12 | **~$0.20–$0.40** |
| **GPU** (`ml.g4dn.xlarge` train, `ml.g5.xlarge` endpoint) | ~$0.20–$0.40 | ~$0.50–$1.00 | **~$0.70–$1.50** |

Default package train step is the **CPU simulation** (same digest/loss schedule as checkpointing) — still billed for the instance time the Processing/Training jobs run. Real Hugging Face fine-tunes (`VULCAN_SAGEMAKER_REAL_TRAIN=1`) need a transformers-enabled image and GPU; that is out of band of the default scripts.

**Always delete the Endpoint** when finished — idle endpoints dominate surprise bills.

## 1. Upload tiny train input

```bash
export AWS_DEFAULT_REGION=us-east-1
export VULCAN_SM_ROLE=arn:aws:iam::ACCOUNT:role/YourSageMakerRole
export VULCAN_SM_BUCKET=your-vulcan-sm-bucket

echo "vulcan reference-tiny-llm train line" | aws s3 cp - \
  "s3://${VULCAN_SM_BUCKET}/vulcan/reference-tiny-llm/train/input.txt"
```

## 2. Upsert the Pipeline

```bash
export VULCAN_ALLOW_LIVE_AWS=1
vulcan-sm-upsert-pipeline \
  --role "$VULCAN_SM_ROLE" \
  --bucket "$VULCAN_SM_BUCKET" \
  --region "$AWS_DEFAULT_REGION"
```

Or:

```bash
python -c "
from sagemaker.workflow.pipeline_context import PipelineSession
import boto3
from vulcan_sagemaker.pipeline import upsert_pipeline
sess = PipelineSession(boto_session=boto3.Session(region_name='us-east-1'))
print(upsert_pipeline(role='$VULCAN_SM_ROLE', bucket='$VULCAN_SM_BUCKET', sagemaker_session=sess))
"
```

## 3. Start an execution

```bash
aws sagemaker start-pipeline-execution \
  --pipeline-name vulcan-reference-tiny-llm \
  --pipeline-parameters \
    Name=ModelApprovalStatus,Value=Approved \
    Name=TrainSteps,Value=20
```

Wait until the execution succeeds (`aws sagemaker list-pipeline-executions --pipeline-name vulcan-reference-tiny-llm`). Note the registered **ModelPackageArn** from the Register step (Console → Model Registry → `vulcan-reference-tiny-llm`, or `list-model-packages`).

### Local dry-run of train/eval (no AWS)

```bash
python -m vulcan_sagemaker.train --output-dir /tmp/vulcan-sm-model --total-steps 20
python -m vulcan_sagemaker.evaluate --model-dir /tmp/vulcan-sm-model --output-dir /tmp/vulcan-sm-eval
cat /tmp/vulcan-sm-eval/evaluation.json
```

## 4. Deploy a real-time Endpoint

```bash
export VULCAN_ALLOW_LIVE_AWS=1
export MODEL_PACKAGE_ARN=arn:aws:sagemaker:...:model-package/vulcan-reference-tiny-llm/...

vulcan-sm-deploy \
  --role "$VULCAN_SM_ROLE" \
  --model-package-arn "$MODEL_PACKAGE_ARN" \
  --endpoint-name vulcan-reference-tiny-llm-rt \
  --instance-type ml.m5.large \
  --wait
```

## 5. Invoke (contract-shaped payload)

```bash
export VULCAN_ALLOW_LIVE_AWS=1
vulcan-sm-invoke \
  --endpoint-name vulcan-reference-tiny-llm-rt \
  --prompt "Hello from Vulcan"
```

Payload matches `POST /v1/infer` llm fields (`modality`, `model_id`, `input.prompt`). Native SageMaker success ≠ full OpenAPI conformance; add a shim if you need the shared conformance suite.

## 6. Tear down (mandatory)

```bash
aws sagemaker delete-endpoint --endpoint-name vulcan-reference-tiny-llm-rt
aws sagemaker delete-endpoint-config --endpoint-config-name <config-from-deploy-output>
# Optional: delete model, pipeline executions artifacts in S3
```

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| CLI exits 2 immediately | `VULCAN_ALLOW_LIVE_AWS` not set to `1` |
| `AccessDenied` on create_training_job | Role missing SageMaker / S3 / pass-role |
| Endpoint stuck `Creating` | Image/model data URI invalid; check CloudWatch logs |
| Want real GPT-2 weights | Build/push a transformers training image and set `VULCAN_SAGEMAKER_REAL_TRAIN=1` (not supported in CI) |
