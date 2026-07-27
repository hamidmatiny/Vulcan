# Known gaps — simulated vs real

Honest inventory as of **v1.1.0 track (phase-17)**. Prefer this over marketing language in READMEs.

## Serving & benchmarks

| Component | Simulated / CPU-dev | Real today |
|-----------|---------------------|------------|
| bentoml / ray-serve / triton / vllm | CPU compose + short k6 artifacts | Contract surface, Dockerfiles, GPU run docs (manual) |
| `benchmark/results/*-cpu.json` | Laptop/CI latency — **not** capacity claims | Schema + compare script |
| Gateway routing | Uses those CPU artifacts + static Bedrock pricing | Selection algorithm + health fallback (ADR-006) |
| KServe | Manifests only in CI; **no** scrape target in compose | Helm chart + kind runbook |

## Managed cloud

| Component | Simulated | Real |
|-----------|-----------|------|
| SageMaker (`pipelines/sagemaker`) | moto in CI | SDK pipeline code + manual runbook (live AWS = human) |
| Bedrock (`bedrock-gateway`) | moto / fake creds; `pricing-reference.json` is **static_reference** | Contract shim shape; pricing file labeled non-live |

## GPU / cluster infra (ADR-002)

| Component | In CI | Gap |
|-----------|-------|-----|
| GPU Operator / MIG / Kueue / Karpenter | template + conftest / terraform plan | **Never applied** by automation |
| Checkpointing library | unit-tested | Needs a real SIGTERM on a GPU training Job to prove e2e |
| Kubeflow Pipelines / Training Operator | compile + validate | Requires **manual** cluster bring-up ([runbook](runbooks/kubeflow-local-kind.md)) |
| TensorRT-LLM / vLLM GPTQ·AWQ·FP8 / speculative decoding | Config + docs only ([ADR-007](adr/007-advanced-gpu-serving-techniques-scope.md)); CI schema/`config.pbtxt` lint | Real `trtllm-build` / GPU measure — [runbook](runbooks/tensorrt-llm-build.md) |

## Observability

| Piece | Live in CPU compose | Gap / honesty |
|-------|---------------------|---------------|
| Prometheus scrape of `/metrics` | bentoml, ray-serve, triton, vllm, gateway, cost-exporter, synthetic-dcgm | KServe (no compose service) |
| Grafana latency/throughput/errors | From `vulcan_infer_*` | — |
| Cost-per-token / cost-per-inference | From cost-exporter (Bedrock pricing-reference **or** ADR-008 `$/GPU-hour` × throughput) | **`$/GPU-hour` not validated against a real cloud invoice** ([ADR-008](adr/008-self-hosted-cost-per-token-assumptions.md)) |
| GPU utilization panels | **LIVE-SYNTHETIC** `DCGM_FI_*` sample series | Real DCGM only after applying phase-7 pools + [`observability/gpu-metrics/helm`](../observability/gpu-metrics/) |
| OTel traces gateway→backend | When collector is up | Backends without `OTEL_*` emit nothing |

~~Former gap: “Replace placeholder GPU panels with DCGM…”~~ — **closed in phase-17** for *wiring*: compose uses synthetic DCGM-shaped metrics; cluster Helm/scrape is real and documented. Remaining gap is **hardware** DCGM on an applied cluster.

## Coverage / security (phase-15)

| Gated (≥65%) | Explicitly not unit-gated (documented reason) |
|--------------|-----------------------------------------------|
| `vulcan_model_contract`, `vulcan_serving_common`, checkpointing, sagemaker, bedrock, vulcan_kfp, `gateway/internal`, cost-exporter | Serving adapters: covered by **conformance + k6**, not pytest line coverage; Helm/Terraform: validate-only; `cmd/gateway` thin main excluded from Go coverpkg |

## What we would build next with a real GPU budget + cluster

1. Apply `infra/terraform/environments/gpu-eks` + GPU Operator/MIG/Kueue/Karpenter to a non-prod account; record cost caps.
2. ~~Replace placeholder GPU panels with DCGM scrapes~~ → **done (synthetic + real Helm)**; next: scrape **real** DCGM on applied nodes and archive under `docs/benchmarks/`.
3. Validate `$/GPU-hour` assumptions in `gpu-hour-assumptions.json` against Cost Explorer / invoice for `g5.xlarge` / `g5.2xlarge` / `p4d.24xlarge`.
4. Add `benchmark/results` for a real KServe shim URL and enable gateway auto-select for kserve.
5. Re-measure Bedrock latency/price from the account (overwrite `pricing-reference.json` with still-labeled measurements).
6. Run Kubeflow train→eval→KServe handoff on the cluster using the existing runbook paths.
7. Wire Alertmanager to a real receiver; tune error-rate burn alerts from production SLOs.
