"""KFP SDK pipeline: train → evaluate → register/handoff to KServe.

Composition (not reinvention):
- **Train (cluster):** Training Operator PyTorchJob submits via Kueue ``lq-training``
  (phase 8) onto Karpenter ``vulcan-gpu-mig-large`` spot (phase 9) with
  ``autoscaling/checkpointing`` resume.
- **Train (component body):** CPU simulation of the same metrics for compile/CI.
- **Evaluate:** same eval_loss/perplexity approach as phase-10 SageMaker.
- **Handoff:** InferenceService YAML matching phase-6 ``serving/kserve`` format.

Note: do not enable ``from __future__ import annotations`` here — KFP inspects
real type objects at decoration time.
"""

from kfp import dsl
from kfp.dsl import Artifact, Input, Output


@dsl.component(base_image="python:3.12-slim")
def train_reference_tiny_llm(total_steps: int, model_dir: Output[Artifact]) -> None:
    """Train step body (CI/local). Cluster runs PyTorchJob — see training-operator/."""
    import json
    from pathlib import Path

    weight_digest = 0
    loss = 1.0
    for step in range(1, int(total_steps) + 1):
        loss = max(0.01, 1.0 / (1.0 + 0.1 * step))
        weight_digest = (weight_digest * 31 + step) % 1_000_000_007
    metrics = {
        "model_id": "reference-tiny-llm",
        "steps": int(total_steps),
        "train_loss": loss,
        "loss": loss,
        "weight_digest": weight_digest,
        "mode": "simulate",
        "checkpointing": "autoscaling/checkpointing",
        "kueue_queue": "lq-training",
        "karpenter_nodepool": "vulcan-gpu-mig-large",
    }
    out = Path(model_dir.path)
    out.mkdir(parents=True, exist_ok=True)
    (out / "train_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (out / "model-meta.json").write_text(
        json.dumps({"format": "vulcan-simulated-checkpoint", "metrics": metrics}, indent=2) + "\n"
    )
    (out / "PYTORCHJOB_REF.txt").write_text(
        "Cluster train: pipelines/kubeflow/training-operator/manifests/"
        "pytorchjob-reference-tiny-llm.yaml\n"
    )


@dsl.component(base_image="python:3.12-slim")
def evaluate_reference_tiny_llm(
    model_dir: Input[Artifact],
    eval_dir: Output[Artifact],
) -> None:
    """Same eval_loss/perplexity approach as phase-10 SageMaker evaluate."""
    import json
    import math
    from pathlib import Path

    metrics = json.loads(Path(model_dir.path, "train_metrics.json").read_text())
    train_loss = float(metrics.get("train_loss", 1.0))
    corpus_tokens = 70
    gap = min(0.5, 0.01 * corpus_tokens)
    eval_loss = train_loss + gap
    perplexity = math.exp(min(eval_loss, 20.0))
    evaluation = {
        "model_id": "reference-tiny-llm",
        "eval_loss": round(eval_loss, 6),
        "perplexity": round(perplexity, 6),
        "backend": "kubeflow",
        "comparison_note": "Aligned with pipelines/sagemaker evaluate_from_train_metrics",
    }
    out = Path(eval_dir.path)
    out.mkdir(parents=True, exist_ok=True)
    (out / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
    (out / "evaluation_report.json").write_text(
        json.dumps(
            {
                "metrics": [
                    {"Name": "eval_loss", "Value": evaluation["eval_loss"]},
                    {"Name": "perplexity", "Value": evaluation["perplexity"]},
                ],
                "model_id": "reference-tiny-llm",
            },
            indent=2,
        )
        + "\n"
    )


@dsl.component(base_image="python:3.12-slim")
def register_and_emit_inferenceservice(
    model_dir: Input[Artifact],
    eval_dir: Input[Artifact],
    handoff_dir: Output[Artifact],
) -> None:
    """Model registry metadata + InferenceService YAML (phase-6 KServe shape)."""
    import json
    from pathlib import Path
    from textwrap import dedent

    evaluation = json.loads(Path(eval_dir.path, "evaluation.json").read_text())
    train_metrics = json.loads(Path(model_dir.path, "train_metrics.json").read_text())
    out = Path(handoff_dir.path)
    out.mkdir(parents=True, exist_ok=True)
    registry = {
        "registry": "vulcan-kubeflow-model-registry",
        "model_id": "reference-tiny-llm",
        "artifact_uri": "s3://vulcan-models/reference-tiny-llm/latest/",
        "eval_loss": evaluation["eval_loss"],
        "perplexity": evaluation["perplexity"],
        "weight_digest": train_metrics.get("weight_digest"),
        "serving": {
            "platform": "kserve",
            "backend": "vllm",
            "manifest": "inferenceservice.yaml",
        },
        "composed_from": {
            "kueue_queue": "lq-training",
            "karpenter_nodepool": "vulcan-gpu-mig-large",
            "checkpointing": "autoscaling/checkpointing",
        },
    }
    (out / "registry.json").write_text(json.dumps(registry, indent=2) + "\n")
    isvc = dedent(
        f"""\
        apiVersion: serving.kserve.io/v1beta1
        kind: InferenceService
        metadata:
          name: vulcan-vllm-finetuned
          namespace: vulcan-serving
          labels:
            app.kubernetes.io/part-of: vulcan
            vulcan.dev/contract: model-contract-v1
            vulcan.dev/backend: vllm
            vulcan.dev/modalities: "llm"
            vulcan.dev/model_id: reference-tiny-llm
            vulcan.dev/trained-by: kubeflow-pipelines
          annotations:
            serving.kserve.io/deploymentMode: RawDeployment
            vulcan.dev/eval_loss: "{evaluation["eval_loss"]}"
            vulcan.dev/perplexity: "{evaluation["perplexity"]}"
        spec:
          predictor:
            minReplicas: 1
            maxReplicas: 3
            containers:
              - name: kserve-container
                image: vulcan-vllm:cpu
                imagePullPolicy: IfNotPresent
                ports:
                  - containerPort: 9004
                    protocol: TCP
                env:
                  - name: PORT
                    value: "9004"
                  - name: VULCAN_RUNTIME_MODE
                    value: "cpu"
                  - name: VLLM_URL
                    value: "http://127.0.0.1:8000"
                readinessProbe:
                  httpGet:
                    path: /health
                    port: 9004
                resources:
                  requests:
                    cpu: 250m
                    memory: 1Gi
              - name: vllm-engine
                image: vulcan-vllm-engine:cpu
                imagePullPolicy: IfNotPresent
                env:
                  - name: VULCAN_RUNTIME_MODE
                    value: "cpu"
                  - name: VULCAN_MODEL_DIR
                    value: "/models/llm/gpt2-small"
                  - name: PORT
                    value: "8000"
                ports:
                  - containerPort: 8000
                    protocol: TCP
                readinessProbe:
                  httpGet:
                    path: /v1/models
                    port: 8000
                resources:
                  requests:
                    cpu: 250m
                    memory: 1Gi
        """
    )
    (out / "inferenceservice.yaml").write_text(isvc)


@dsl.pipeline(
    name="vulcan-reference-tiny-llm",
    description=(
        "Train reference-tiny-llm (PyTorchJob via Kueue+Karpenter+checkpointing), "
        "evaluate (SageMaker-aligned metrics), hand off InferenceService (KServe)."
    ),
)
def vulcan_reference_tiny_llm_pipeline(total_steps: int = 20) -> None:
    train_task = train_reference_tiny_llm(total_steps=total_steps)
    eval_task = evaluate_reference_tiny_llm(model_dir=train_task.outputs["model_dir"])
    register_and_emit_inferenceservice(
        model_dir=train_task.outputs["model_dir"],
        eval_dir=eval_task.outputs["eval_dir"],
    )
