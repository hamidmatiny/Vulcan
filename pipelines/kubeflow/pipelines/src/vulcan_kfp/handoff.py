"""Register metadata + emit InferenceService YAML matching phase-6 KServe format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vulcan_kfp.pins import MODEL_ID, load_reference_llm_pin

# Mirrors serving/kserve/helm values for the vLLM InferenceService (LLM handoff).
ISVC_TEMPLATE = """\
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: {name}
  namespace: {namespace}
  labels:
    app.kubernetes.io/part-of: vulcan
    vulcan.dev/contract: model-contract-v1
    vulcan.dev/backend: vllm
    vulcan.dev/modalities: "llm"
    vulcan.dev/model_id: {model_id}
    vulcan.dev/trained-by: kubeflow-pipelines
  annotations:
    serving.kserve.io/deploymentMode: RawDeployment
    vulcan.dev/pipeline: vulcan-reference-tiny-llm
    vulcan.dev/eval_loss: "{eval_loss}"
    vulcan.dev/perplexity: "{perplexity}"
spec:
  predictor:
    minReplicas: 1
    maxReplicas: 3
    containers:
      - name: kserve-container
        image: {shim_image}
        imagePullPolicy: IfNotPresent
        ports:
          - containerPort: 9004
            protocol: TCP
        env:
          - name: PORT
            value: "9004"
          - name: HOST
            value: "0.0.0.0"
          - name: VULCAN_RUNTIME_MODE
            value: "cpu"
          - name: VLLM_URL
            value: "http://127.0.0.1:8000"
          - name: VLLM_WAIT_SECONDS
            value: "300"
        readinessProbe:
          httpGet:
            path: /health
            port: 9004
          initialDelaySeconds: 10
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health
            port: 9004
          initialDelaySeconds: 30
          periodSeconds: 20
        resources:
          requests:
            cpu: 250m
            memory: 1Gi
          limits:
            cpu: "2"
            memory: 4Gi
      - name: vllm-engine
        image: {engine_image}
        imagePullPolicy: IfNotPresent
        env:
          - name: VULCAN_RUNTIME_MODE
            value: "cpu"
          - name: VULCAN_MODEL_DIR
            value: "{model_mount}"
          - name: PORT
            value: "8000"
          - name: HOST
            value: "0.0.0.0"
        ports:
          - containerPort: 8000
            protocol: TCP
        readinessProbe:
          httpGet:
            path: /v1/models
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 10
        resources:
          requests:
            cpu: 250m
            memory: 1Gi
          limits:
            cpu: "2"
            memory: 4Gi
"""


def build_inferenceservice_yaml(
    *,
    evaluation: dict[str, Any],
    name: str = "vulcan-vllm-finetuned",
    namespace: str = "vulcan-serving",
    shim_image: str = "vulcan-vllm:cpu",
    engine_image: str = "vulcan-vllm-engine:cpu",
    model_mount: str = "/models/llm/gpt2-small",
) -> str:
    return ISVC_TEMPLATE.format(
        name=name,
        namespace=namespace,
        model_id=MODEL_ID,
        eval_loss=evaluation["eval_loss"],
        perplexity=evaluation["perplexity"],
        shim_image=shim_image,
        engine_image=engine_image,
        model_mount=model_mount,
    )


def register_and_handoff(
    *,
    model_dir: Path,
    eval_dir: Path,
    output_dir: Path,
    artifact_uri: str = "s3://vulcan-models/reference-tiny-llm/latest/",
) -> dict[str, Any]:
    """Write registry metadata + InferenceService manifest (training→serving handoff)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pin = load_reference_llm_pin()
    evaluation = json.loads((eval_dir / "evaluation.json").read_text(encoding="utf-8"))
    train_metrics_path = model_dir / "train_metrics.json"
    train_metrics = (
        json.loads(train_metrics_path.read_text(encoding="utf-8"))
        if train_metrics_path.is_file()
        else {}
    )

    registry = {
        "registry": "vulcan-kubeflow-model-registry",
        "model_id": MODEL_ID,
        "revision": pin.revision,
        "hub_repo_id": pin.repo_id,
        "artifact_uri": artifact_uri,
        "eval_loss": evaluation["eval_loss"],
        "perplexity": evaluation["perplexity"],
        "weight_digest": train_metrics.get("weight_digest"),
        "serving": {
            "platform": "kserve",
            "backend": "vllm",
            "manifest": "inferenceservice.yaml",
            "chart_format": "serving/kserve/helm (phase-6)",
        },
        "composed_from": {
            "kueue_queue": "lq-training",
            "karpenter_nodepool": "vulcan-gpu-mig-large",
            "checkpointing": "autoscaling/checkpointing",
        },
    }
    (output_dir / "registry.json").write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    isvc = build_inferenceservice_yaml(evaluation=evaluation)
    (output_dir / "inferenceservice.yaml").write_text(isvc, encoding="utf-8")
    return registry
