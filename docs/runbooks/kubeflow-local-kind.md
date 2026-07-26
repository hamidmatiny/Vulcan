# Runbook: Vulcan Kubeflow Pipelines + Training Operator on kind

**Manual only.** CI compiles the KFP pipeline and validates manifests with kubeconform/conftest — it **never** installs Kubeflow, Training Operator, Kueue, or Karpenter, and **never** applies these CRs ([ADR-002](../adr/002-gpu-cost-safety-policy.md)).

> **Do not add this apply flow to CI.** GPU/node-pool cost and cluster flake risk are exactly what ADR-002 forbids in automation.

This runbook closes the loop: **PyTorchJob (Kueue + Karpenter + checkpointing) → eval metrics → KServe InferenceService**, composing phases 6–9 rather than reinstalling them from scratch.

## Prerequisites

- Docker + [kind](https://kind.sigs.k8s.io/) (or minikube)
- `kubectl`, `helm`
- Images for serving handoff (phase 4/5): `vulcan-vllm:cpu`, `vulcan-vllm-engine:cpu`
- Optional GPU nodes: only if you want a real MIG/spot path; otherwise the PyTorchJob will Pending (still useful to inspect scheduling labels)

Validate first (same as CI):

```bash
make validate-kubeflow
```

## 1. Create a cluster

```bash
kind create cluster --name vulcan-kf
kubectl cluster-info --context kind-vulcan-kf
```

## 2. Install platform pieces (out of band)

Versions drift — pin from upstream docs for your date. Sketch:

| Piece | Role in this phase |
|-------|--------------------|
| Kubeflow Pipelines | Run compiled `vulcan-reference-tiny-llm.yaml` |
| Training Operator | Owns `PyTorchJob` |
| Kueue (phase 8 chart) | Admits jobs on `lq-training` |
| KServe (phase 6) | Serves handoff InferenceService |
| Karpenter + GPU Operator (phases 7–9) | Only on a real cloud cluster; kind usually skips |

Kueue queues (from repo, validate-only chart — apply manually):

```bash
helm template vulcan-kueue gpu-infra/kueue/chart | kubectl apply -f -
# Ensure LocalQueue lq-training exists in team-training
kubectl get localqueue -A
```

KServe (see also [`kserve-local-kind.md`](./kserve-local-kind.md)):

```bash
# cert-manager + KServe CRDs/controller (upstream quickstart)
helm upgrade --install vulcan-kserve ./serving/kserve/helm \
  --namespace vulcan-serving --create-namespace
```

Training Operator + KFP: follow current Kubeflow / Training Operator install guides for your version.

## 3. Build / load the training image

The PyTorchJob expects `vulcan/training-checkpoint:phase-12` wrapping `vulcan-checkpoint-finetune` from `autoscaling/checkpointing`. For a kind smoke you can retag a locally built image that installs that package, or temporarily edit the image field to your registry.

```bash
# Example sketch — adapt to your Dockerfile
kind load docker-image vulcan/training-checkpoint:phase-12 --name vulcan-kf
kind load docker-image vulcan-vllm:cpu vulcan-vllm-engine:cpu --name vulcan-kf
```

## 4. Apply the PyTorchJob (train via Kueue)

```bash
kubectl apply -f pipelines/kubeflow/training-operator/manifests/pytorchjob-reference-tiny-llm.yaml
kubectl get pytorchjob -n team-training
kubectl describe pytorchjob vulcan-finetune-reference-tiny-llm -n team-training
# Confirm Kueue Workload admitted:
kubectl get workloads -n team-training
```

On spot interruption / Kueue preemption, the process should checkpoint under `/checkpoints` (phase-9 contract) and resume on restart.

## 5. Run the KFP pipeline (eval + handoff)

Upload/compile already done locally:

```bash
# Artifact from make validate-kubeflow:
ls pipelines/kubeflow/pipelines/compiled/vulcan-reference-tiny-llm.yaml
```

Create a KFP run in your cluster’s Pipelines UI/API pointing at that YAML (or `kfp` CLI `run create`). The register step writes `registry.json` + `inferenceservice.yaml` into the handoff artifact.

Alternatively, generate handoff locally without KFP UI:

```bash
cd pipelines/kubeflow/pipelines && .venv/bin/python - <<'PY'
from pathlib import Path
from vulcan_kfp.train import run_training
from vulcan_kfp.evaluate import evaluate_from_train_metrics, write_evaluation
from vulcan_kfp.handoff import register_and_handoff
m = Path("/tmp/vulcan-kf/model"); e = Path("/tmp/vulcan-kf/eval"); h = Path("/tmp/vulcan-kf/handoff")
run_training(output_dir=m, total_steps=20)
write_evaluation(e, evaluate_from_train_metrics(__import__("json").loads((m/"train_metrics.json").read_text())))
print(register_and_handoff(model_dir=m, eval_dir=e, output_dir=h))
print((h/"inferenceservice.yaml").read_text()[:400])
PY
```

## 6. Apply InferenceService handoff (serving)

```bash
kubectl apply -f /tmp/vulcan-kf/handoff/inferenceservice.yaml
# or the static template:
# kubectl apply -f pipelines/kubeflow/pipelines/handoff/inferenceservice-reference-tiny-llm.yaml
kubectl get isvc -n vulcan-serving
kubectl port-forward -n vulcan-serving svc/vulcan-vllm-finetuned-predictor 9005:9004
curl -sS http://127.0.0.1:9005/health
```

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| PyTorchJob Pending forever | No nodes matching `vulcan.dev/gpu-pool=mig-large` (expected on CPU-only kind) |
| Workload stuck QuotaReserved | Kueue ClusterQueue `cq-training` missing or MIG quota exhausted |
| Pod dies without checkpoint | Image missing `vulcan-checkpoint-finetune`; PVC not bound |
| InferenceService not Ready | vLLM images not loaded into kind; check `kubectl describe isvc` |
| Tempted to “just add kubectl apply to CI” | **Stop** — ADR-002; keep validate-only |

## Tear down

```bash
kubectl delete -f pipelines/kubeflow/training-operator/manifests/pytorchjob-reference-tiny-llm.yaml --ignore-not-found
kubectl delete isvc vulcan-vllm-finetuned -n vulcan-serving --ignore-not-found
kind delete cluster --name vulcan-kf
```
