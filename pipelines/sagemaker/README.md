# sagemaker

**Path:** `pipelines/sagemaker/`  
**Phase:** 10  
**Model:** phase-1 pin `reference-tiny-llm` (GPT-2 small — same `models/pins.json` revision as every serving backend)

## Purpose

SageMaker **Pipelines** (train → evaluate → register), **Model Registry**, and a real-time **Endpoint** example for the Vulcan reference LLM. This is a managed comparison point against self-hosted `serving/*` adapters — same model identity and evaluation vocabulary, not a disconnected demo.

CI never calls a live AWS account ([ADR-002](../../docs/adr/002-gpu-cost-safety-policy.md)). Tests use **moto** to mock SageMaker/S3/IAM. Manual steps: [`docs/runbooks/sagemaker-manual-run.md`](../../docs/runbooks/sagemaker-manual-run.md).

## Contract vocabulary mapping

SageMaker is managed AWS; Vulcan still uses the phase-0 contract *concepts*. Mapping:

| Contract concept | Self-hosted (`serving/*`) | SageMaker (this package) |
|------------------|---------------------------|---------------------------|
| **Backend** | `bentoml` / `triton` / `vllm` / … | `sagemaker` (`config.BACKEND_ID`) |
| **resource-requirements manifest** | `serving/*/resource-requirements.json` + `GET /v1/resources` | [`resource-requirements.json`](./resource-requirements.json) (same schema); Endpoint instance type is the runtime resource claim |
| **Health** | `GET /health` → `status: ok\|starting\|error` | Endpoint status `InService` / `Creating` / `Failed` (`DescribeEndpoint`) |
| **Metrics** | `GET /metrics` (Prometheus) | CloudWatch metrics for the Endpoint + Model Registry `eval_loss` / `perplexity` from the evaluate step |
| **Infer** | `POST /v1/infer` (`modality=llm`) | `InvokeEndpoint` with the **same JSON shape** (`invoke.build_infer_request`) — put a thin contract shim in front if you need byte-identical OpenAPI conformance |
| **Model identity** | `model_id=reference-tiny-llm` + MANIFEST sha256 | Same `model_id` + HF `revision` from `models/pins.json` stamped on packages/tags |

Training-quality gate here is **eval_loss / perplexity** on a fixed corpus (counterpart to serving’s shared k6 latency harness). Cross-backend *serving* comparison still uses `benchmark/` against contract HTTP; SageMaker native invoke is the managed equivalent of `/v1/infer`.

## Layout

```text
src/vulcan_sagemaker/
  pipeline.py     SageMaker SDK Pipeline (train → evaluate → register)
  train.py        Train step (CPU simulation by default)
  evaluate.py     eval_loss + perplexity
  registry.py     Model Package Group + package version
  deploy.py       Real-time Endpoint from package ARN
  invoke.py       Contract-shaped InvokeEndpoint helper
  cli.py          Manual AWS CLIs (require VULCAN_ALLOW_LIVE_AWS=1)
tests/            moto + unit tests (≥65% coverage)
resource-requirements.json
```

## Local tests (CI)

```bash
make test-sagemaker
```

## Manual AWS

See the [runbook](../../docs/runbooks/sagemaker-manual-run.md). Approx smoke cost is printed by the upsert CLI and detailed there — delete the Endpoint when finished.
