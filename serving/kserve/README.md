# serving/kserve

Kubernetes-native packaging for Vulcan’s phase-0 **model contract**, using [KServe](https://kserve.github.io/) `InferenceService` objects that wrap the **phase-4 Triton** and **phase-5 vLLM** container images as predictors.

This phase is **not** another docker-compose backend. There is no host port in `9000–9099` for compose. CI validates manifests only ([ADR-002](../../docs/adr/002-gpu-cost-safety-policy.md)).

## How KServe differs from bentoml / ray-serve / triton / vllm adapters

| | **Phases 2–5 adapters** | **This directory (KServe)** |
|--|-------------------------|-----------------------------|
| Runtime home | Process / Docker Compose on a laptop | Kubernetes API (`InferenceService`) |
| North-bound API | Each adapter implements `/health` `/metrics` `/v1/infer` in-process | Same contract, served by containers KServe schedules |
| Scaling | Framework replicas (Bento/Ray) or process count | Knative Serverless **or** raw Deployment + HPA (`deploymentMode`) |
| Rollouts | Rebuild/restart compose service | `canaryTrafficPercent` between revisions |
| CI | Live CPU container + conformance + k6 | `helm template` + kubeconform + conftest — **no apply** |
| Metrics / traces | Process exposes `/metrics`; OTel when `OTEL_*` set | Scrape the **scheduled adapter** Pod (triton/vllm shim). No separate kserve `/metrics` binary — see [`observability/`](../../observability/) |

### InferenceService / InferenceGraph mental model

```text
 Client / gateway
        │
        ▼
 ┌──────────────────────────────────────┐
 │  InferenceService (KServe control)   │
 │  predictor | transformer | explainer │
 └──────────────────┬───────────────────┘
                    │ schedules Pod(s)
                    ▼
 ┌──────────────────────────────────────┐
 │  predictor containers (Vulcan)       │
 │  kserve-container = contract shim    │
 │  + engine sidecar (Triton / vLLM)    │
 └──────────────────────────────────────┘
```

- **Predictor** — runs the model-serving containers (here: Vulcan contract shims + engines).
- **Transformer** (optional) — pre/post-process; not required because shims already speak the Vulcan contract.
- **Explainer** (optional) — model explanations; out of scope for phase-6.
- **InferenceGraph** — DAG of InferenceServices for multi-step pipelines; future option to fan llm vs vision to vLLM vs Triton. Not shipped in this chart yet.

KServe is a **deployment + traffic plane**, not a competing inference engine. **Triton** and **vLLM** remain the backing runtimes; KServe wraps their Vulcan images and adds K8s autoscaling, revisions, and canaries.

## Chart layout

```text
serving/kserve/
  helm/                 Helm chart (InferenceServices)
    values.yaml         CPU-dev defaults
    values-canary.yaml  Example 10% canaryTrafficPercent
  policy/               OPA/conftest policies + unit tests
  scripts/validate.sh   helm template → kubeconform → conftest
```

Rendered services:

| InferenceService | Backend images | Contract modalities |
|------------------|----------------|---------------------|
| `vulcan-triton` | `vulcan-triton` + `vulcan-triton-engine` | llm + vision |
| `vulcan-vllm` | `vulcan-vllm` + `vulcan-vllm-engine` | **llm only** |

## Canary rollout

`values-canary.yaml` sets `canaryTrafficPercent: 10` and switches shim/engine images to `*:cpu-canary` tags (new revision). KServe splits traffic between the last stable revision and the canary ([KServe canary docs](https://kserve.github.io/website/docs/model-serving/predictive-inference/rollout-strategies/canary-example)).

```bash
helm template vulcan-kserve ./serving/kserve/helm \
  -f serving/kserve/helm/values.yaml \
  -f serving/kserve/helm/values-canary.yaml
```

## Validate (CI / local)

```bash
make validate-kserve
```

Requires: `helm`, `kubeconform`, `conftest`. Never runs `helm upgrade` or `kubectl apply`.

## Manual cluster bring-up

See [`docs/runbooks/kserve-local-kind.md`](../../docs/runbooks/kserve-local-kind.md) (kind/minikube + KServe install + port-forward on **9005**).
