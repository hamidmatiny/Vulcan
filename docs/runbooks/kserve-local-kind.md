# Runbook: Vulcan KServe on local kind (or minikube)

**Manual only.** CI never applies these manifests ([ADR-002](../adr/002-gpu-cost-safety-policy.md)). Use this when you want a real cluster exercise of `serving/kserve/helm`.

Assumes Docker Desktop (or equivalent) and that you have already built the phase-4/5 images:

```bash
make models-export
make triton-prepare
docker compose build triton-engine triton vllm-engine vllm
```

## 1. Create a cluster

### kind

```bash
kind create cluster --name vulcan
kubectl cluster-info --context kind-vulcan
```

Load images into kind (they are not pulled from a registry by default):

```bash
kind load docker-image vulcan-triton:cpu vulcan-triton-engine:cpu \
  vulcan-vllm:cpu vulcan-vllm-engine:cpu --name vulcan
```

### minikube (alternative)

```bash
minikube start --driver=docker
eval "$(minikube docker-env)"
# rebuild images inside minikube's docker, or minikube image load …
docker compose build triton-engine triton vllm-engine vllm
```

## 2. Install KServe

Follow the current [KServe quickstart](https://kserve.github.io/website/docs/getting-started/quickstart-guide/) for your version. Minimal sketch (versions drift — pin from upstream docs):

```bash
# Example: cert-manager + KServe (Serverless needs Knative; we use RawDeployment)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.4/cert-manager.yaml
kubectl wait --for=condition=Available --timeout=300s -n cert-manager deployment/cert-manager-webhook

# Install KServe CRDs + controller (check upstream for the exact release URL)
kubectl apply -f https://github.com/kserve/kserve/releases/download/v0.13.0/kserve.yaml
kubectl wait --for=condition=Available --timeout=300s -n kserve deployment/kserve-controller-manager
```

This chart sets `serving.kserve.io/deploymentMode: RawDeployment` so **Knative Serving is not required**. If you prefer Serverless, install Knative and change `deploymentMode` in values.

## 3. Render and apply the chart

Validate first (same as CI):

```bash
make validate-kserve
```

Apply (manual):

```bash
helm upgrade --install vulcan-kserve ./serving/kserve/helm \
  --namespace vulcan-serving \
  --create-namespace \
  --wait --timeout 10m
```

Canary example (10% to `*:cpu-canary` tags — load those images too if you use them):

```bash
helm upgrade --install vulcan-kserve ./serving/kserve/helm \
  --namespace vulcan-serving \
  -f serving/kserve/helm/values.yaml \
  -f serving/kserve/helm/values-canary.yaml \
  --wait
```

Check status:

```bash
kubectl get isvc -n vulcan-serving
kubectl describe isvc vulcan-triton -n vulcan-serving
kubectl get pods -n vulcan-serving
```

## 4. Hit the Vulcan contract

Port-forward the Triton InferenceService (host port **9005** — inside Vulcan’s `9000–9099` range):

```bash
kubectl port-forward -n vulcan-serving svc/vulcan-triton-predictor 9005:9003
# Service name may vary slightly by KServe version / deploymentMode — check:
# kubectl get svc -n vulcan-serving
```

```bash
curl -sS http://127.0.0.1:9005/health
VULCAN_BACKEND_URL=http://127.0.0.1:9005 make test-serving-common
```

For vLLM (LLM-only):

```bash
kubectl port-forward -n vulcan-serving svc/vulcan-vllm-predictor 9006:9004
VULCAN_BACKEND_URL=http://127.0.0.1:9006 VULCAN_CONFORMANCE_MODALITIES=llm make test-serving-common
```

## 5. Tear down

```bash
helm uninstall vulcan-kserve -n vulcan-serving || true
kind delete cluster --name vulcan
```

## Troubleshooting

| Symptom | Check |
|---------|--------|
| InferenceService not Ready | `kubectl describe isvc …`; image pull / `kind load` |
| Shim 503 | Engine sidecar not ready; logs on `triton-engine` / `vllm-engine` |
| No Service named `*-predictor` | RawDeployment vs Serverless naming — `kubectl get svc -A \| grep vulcan` |
| Canary not splitting | Need a prior stable revision at 100%; see KServe canary docs |

Do not add this apply flow to GitHub Actions.
