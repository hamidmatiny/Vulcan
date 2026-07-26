# bedrock-gateway

**Path:** `bedrock-gateway/`  
**Phase:** 11  
**Honesty bar:** This is a **thin, vocabulary-and-judgment** adapter — not a deep Bedrock platform. Same spirit as [phase 10’s SageMaker README](../pipelines/sagemaker/README.md): contract-shaped so the (phase-13) router can select `backend=bedrock` without a special case, with clear limits on conformance and pricing accuracy.

## Purpose

Expose AWS Bedrock foundation-model `InvokeModel` behind the **same phase-0 LLM-branch contract** as [`serving/vllm`](../serving/vllm/):

| Endpoint | Behavior |
|----------|----------|
| `GET /health` | Config readiness (`status=ok`); does **not** ping Bedrock (would need live creds / spend) |
| `GET /metrics` | Prometheus counters/histograms (`backend=bedrock`) |
| `GET /v1/resources` | [`resource-requirements.json`](./resource-requirements.json) |
| `GET /v1/pricing-reference` | Static $/1K tokens + typical latency for the future router |
| `POST /v1/infer` | `modality=llm` only → Bedrock; `vision` → `unsupported_modality` (like vLLM) |

`model_id` is a **Bedrock foundation model id** (e.g. `amazon.titan-text-express-v1`), not the phase-1 GPT-2 pin. Self-hosted pin comparison stays on `serving/*`.

Optional local listen port: **9006** (Vulcan 9000–9099 range). **No docker-compose** service — not wired into `make up`.

## When to use Bedrock vs self-hosted (plain English)

For a hiring manager / platform lead deciding “managed API vs this repo’s GPU stack”:

| Choose **Bedrock** when… | Choose a **self-hosted Vulcan backend** (`vllm` / `triton` / …) when… |
|--------------------------|---------------------------------------------------------------------|
| You need a **foundation model you don’t want to operate** (Claude, Titan, etc.) with AWS IAM + VPC endpoints | You need the **phase-1 reference pin** (`reference-tiny-llm`) for apples-to-apples benchmarks across adapters |
| **Data residency / procurement** already prefers AWS managed AI, and Model Access is approved | You need **MIG, Kueue, Karpenter spot**, or other GPU orchestration this repo already models |
| Traffic is **bursty / low volume** and ops cost of a GPU pool would dominate | Traffic is **steady and high** — at scale, owned GPUs often beat token APIs on unit cost (measure; don’t guess) |
| Latency of a **regional managed round-trip** (~hundreds of ms typical) is acceptable | You need **lowest possible p95** next to your app (in-cluster GPU) |
| Model catalog on Bedrock covers the product need | You need a **custom fine-tune / ONNX / TensorRT** path this repo’s serving stack owns |

**Not a claim:** Bedrock is not “better” or “worse” in the abstract. It’s a **different control plane**. This adapter exists so the router can treat it as one more backend string, not so Vulcan pretends Bedrock is a GPU Operator replacement.

## Static pricing & latency (router fodder)

[`pricing-reference.json`](./pricing-reference.json) holds **static, clearly labeled** `input_usd_per_1k_tokens`, `output_usd_per_1k_tokens`, and `typical_latency_ms` (`p50` / `p95`).  

- **Not** live AWS Pricing API  
- **Not** suitable for customer billing  
- How to replace with real account measurements is documented in that file and exposed at `GET /v1/pricing-reference`

## Tests (CI — no live Bedrock)

```bash
make test-bedrock
```

Uses fake AWS credentials + moto (session) with `invoke_model` stubbed — same pattern as phase-10 SageMaker CI. No network calls to AWS.

## Local run (optional, your credentials)

```bash
cd bedrock-gateway && python3 -m venv .venv && . .venv/bin/activate
pip install -e "../../contracts/model-contract[dev]" -e ".[dev]"
export AWS_DEFAULT_REGION=us-east-1
export BEDROCK_MODEL_ID=amazon.titan-text-express-v1
# Enable model access in the Bedrock console first.
vulcan-bedrock-gateway   # :9006
```

Live invokes **cost money**. Prefer mocked tests unless you intentionally want a manual smoke.

## Limits (read before over-claiming)

- LLM-only; no streaming; no Converse API yet  
- Provider payload mapping covers Titan + Claude InvokeModel shapes; other model families may need a one-line mapper  
- `/health` does not prove model access in the account  
- Not part of the shared k6 CI matrix (managed spend — ADR-002)
