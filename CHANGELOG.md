# Changelog

All notable changes to Vulcan are documented here.

## [1.2.0] — 2026-07-27

v1.2.0 close-out: advanced GPU packaging (validate-only), cost-per-token, training backends,
LoRA/PEFT, DVC for deterministic exports, pluggable experiment tracking, and a tool-grounded
LangGraph advisor with non-fabrication CI. Feature commits:

### Phase commits (16–22)

| Phase | Commit | Summary |
|------:|--------|---------|
| 16 | [`96cb7e1`](https://github.com/hamidmatiny/Vulcan/commit/96cb7e1) | Advanced GPU serving — GPTQ/AWQ/FP8 + TensorRT-LLM templates |
| 17 | [`164ef1a`](https://github.com/hamidmatiny/Vulcan/commit/164ef1a) | Cost-per-token + GPU utilization tracking |
| 18 | [`179a1cc`](https://github.com/hamidmatiny/Vulcan/commit/179a1cc) | Training backends + training-job contract |
| 19 | [`21d590b`](https://github.com/hamidmatiny/Vulcan/commit/21d590b) | LoRA/PEFT adapter fine-tuning + transparent serving |
| 20 | [`baa2ba4`](https://github.com/hamidmatiny/Vulcan/commit/baa2ba4) | DVC for deterministic model exports |
| 21 | [`3e81029`](https://github.com/hamidmatiny/Vulcan/commit/3e81029) | Pluggable experiment tracking (MLflow + W&B offline) |
| 22 | [`c61e16c`](https://github.com/hamidmatiny/Vulcan/commit/c61e16c) | LangGraph advisor — tool-grounded, non-fabrication |

### Phase 22 — LangGraph advisor (tool-grounded, non-fabrication)

- `advisor/`: LangGraph with `query_prometheus`, `read_benchmark_results`, `query_routing_history`, `recommend` (ADR-014)
- Synthesis via template + optional pinned `reference-tiny-llm`; no paid LLM API in CI
- CI asserts every numeric/backend claim in the answer appears in that run’s tool evidence (extends ADR-007)

### Phase 21 — Pluggable experiment tracking (MLflow + W&B offline)

*Feature commit [`3e81029`](https://github.com/hamidmatiny/Vulcan/commit/3e81029); artifact-serve fix [`62510a7`](https://github.com/hamidmatiny/Vulcan/commit/62510a7).*

- `training/common/tracking.py`: `ExperimentTracker` interface; `MlflowTracker` + `WandbTracker` (offline-only); default `VULCAN_TRACKER_BACKEND=none` (ADR-013)
- FSDP/DDP + LoRA report existing loss/throughput through the interface (no recomputation)
- Compose MLflow on host port **9014**; CI asserts MLflow API metrics + W&B `offline-run-*` dir (never wandb.ai)

### Phase 20 — DVC data versioning (deterministic model exports)

*Feature commit [`baa2ba4`](https://github.com/hamidmatiny/Vulcan/commit/baa2ba4).*

- `dvc.yaml` wraps existing `export_llm.py` / `export_vision.py`; local filesystem remote only in CI (ADR-012)
- Cross-check: DVC-tracked primary outs' SHA256 must match `sha256sums.txt` / MANIFEST (does not replace MANIFEST)
- Scope: deterministic reference exports only — no training/adapter content-hash tracking (extends ADR-009 / ADR-011)
- CI `dvc-repro` job: `dvc repro` + clean `dvc status` + unchanged `dvc.lock`

### Phase 19 — LoRA / PEFT (adapter fine-tuning + transparent serving)

*Feature commit [`21d590b`](https://github.com/hamidmatiny/Vulcan/commit/21d590b).*

- `LoraFineTuneSpec` / `LoraFineTuneResult` in `contracts/training-job-contract/` (ADR-011; extends ADR-010)
- `training/fsdp-ddp/lora/`: CPU PEFT fine-tune on pinned `reference-tiny-llm`; structural adapter verify (no SHA256 pin — ADR-009)
- BentoML optionally serves `reference-tiny-llm-lora-demo` through unchanged `/v1/infer` (ADR-001)
- CI: logits delta proof (base vs base+adapter) on a fixed prompt

### Phase 18 — Training backends (v1.2.0 track)

*Feature commit [`179a1cc`](https://github.com/hamidmatiny/Vulcan/commit/179a1cc).*

- `contracts/training-job-contract/`: `TrainingJobSpec` / `TrainingJobResult` OpenAPI + JSON Schema (ADR-010)
- `training/{ray-train,fsdp-ddp,deepspeed}/`: CPU-simulated distributed training (`gloo`, world_size=2; ADR-009)
- FSDP/DDP SIGTERM → checkpoint → resume test; DeepSpeed ZeRO-1/2 CPU path + [GPU runbook](./docs/runbooks/deepspeed-gpu-mode.md)
- Cost-exporter: `vulcan_estimated_cost_usd_per_training_step` from training results × ADR-008 `$/GPU-hour`
- Host ports **9011–9013** (compose profile `training`); ADR-009 / ADR-010

### Phase 17 — Cost-per-token and GPU utilization tracking

*Feature commit [`164ef1a`](https://github.com/hamidmatiny/Vulcan/commit/164ef1a).*

- `observability/gpu-metrics/`: real DCGM-exporter Helm values + cluster Prometheus scrape for phase-7 pools; synthetic DCGM-shaped exporter for compose/CI
- Cost-exporter: `vulcan_estimated_cost_usd_per_token` from Bedrock `pricing-reference.json` and ADR-008 `$/GPU-hour` × benchmark throughput (phase-7 instance types only)
- Grafana: cost-per-token + LIVE-SYNTHETIC GPU util panels; LIVE vs PLACEHOLDER table updated
- [ADR-008](./docs/adr/008-self-hosted-cost-per-token-assumptions.md); KNOWN_GAPS #2 closed; CI smoke asserts cost-per-token + synthetic DCGM

### Phase 16 — Advanced GPU serving (v1.1.0 track)

*Feature commit [`96cb7e1`](https://github.com/hamidmatiny/Vulcan/commit/96cb7e1).*

- Extended `serving/vllm/docs/gpu-mode.md`: continuous batching, PagedAttention vs CPU KV, speculative decoding pairs
- `serving/vllm/gpu-variants/{gptq,awq,fp8}/`: schema-valid resource manifests (`supports_quantization`, declared VRAM envelopes)
- `serving/triton/tensorrt-llm/`: TensorRT-LLM `config.pbtxt` template + Dockerfile + [runbook](./docs/runbooks/tensorrt-llm-build.md)
- [ADR-007](./docs/adr/007-advanced-gpu-serving-techniques-scope.md); adr-gate; CI validate-only (no GPU, no invented numbers)

## [1.0.0] — 2026-07-26

Release hardening: security scans, docs site, coverage extensions, demo/case-study honesty docs. Tag: `v1.0.0`.

### Phase 15 — Security hardening, docs site, and v1.0.0 release

*Feature commit [`cba0197`](https://github.com/hamidmatiny/Vulcan/commit/cba0197); tag `v1.0.0` includes the follow-up changelog hash fix.*

- Trivy (CRITICAL, ignore-unfixed) + Syft SBOM on built images: bentoml, ray-serve, triton, triton-engine, vllm, vllm-engine, gateway, cost-exporter
- Semgrep (`p/python`, `p/golang`) across serving/gateway/pipelines Python + Go
- Coverage gate ≥65% extended to `gateway/internal` and `observability/cost-exporter`; exemptions documented in CONTRIBUTING + KNOWN_GAPS
- MkDocs Material site wiring existing READMEs + ADRs 001–006 (`make docs-serve`)
- `docs/DEMO_SCRIPT.md`, `docs/CASE_STUDY.md`, `docs/KNOWN_GAPS.md` (commands verified against the live CPU stack)

### Phase commits (0–15)

| Phase | Commit | Summary |
|------:|--------|---------|
| 0 | [`bd92ee4`](https://github.com/hamidmatiny/Vulcan/commit/bd92ee4) | Foundations, model contract, CI skeleton |
| 1 | [`e8d1e88`](https://github.com/hamidmatiny/Vulcan/commit/e8d1e88) | Reference models and benchmark harness |
| 2 | [`c7f7a02`](https://github.com/hamidmatiny/Vulcan/commit/c7f7a02) | BentoML adapter |
| 3 | [`181c72c`](https://github.com/hamidmatiny/Vulcan/commit/181c72c) | Ray Serve adapter |
| 4 | [`3e35d86`](https://github.com/hamidmatiny/Vulcan/commit/3e35d86) | Triton adapter |
| 5 | [`54c5bb0`](https://github.com/hamidmatiny/Vulcan/commit/54c5bb0) | vLLM adapter |
| 6 | [`372dc19`](https://github.com/hamidmatiny/Vulcan/commit/372dc19) | KServe adapter |
| 7 | [`c5c4fdf`](https://github.com/hamidmatiny/Vulcan/commit/c5c4fdf) | GPU Operator, device plugin, MIG |
| 8 | [`ba466fc`](https://github.com/hamidmatiny/Vulcan/commit/ba466fc) | Kueue multi-tenant GPU scheduling |
| 9 | [`856277f`](https://github.com/hamidmatiny/Vulcan/commit/856277f) | Karpenter GPU autoscaling and checkpoint-resume |
| 10 | [`559203d`](https://github.com/hamidmatiny/Vulcan/commit/559203d) | SageMaker Pipelines, Endpoints, Model Registry |
| 11 | [`eece3f6`](https://github.com/hamidmatiny/Vulcan/commit/eece3f6) | Bedrock-aware gateway adapter |
| 12 | [`cf0c480`](https://github.com/hamidmatiny/Vulcan/commit/cf0c480) | Kubeflow Pipelines + Training Operator → KServe |
| 13 | [`3d83fe3`](https://github.com/hamidmatiny/Vulcan/commit/3d83fe3) | Routing gateway and benchmark-driven selection |
| 14 | [`04beccb`](https://github.com/hamidmatiny/Vulcan/commit/04beccb) | Observability — tracing, metrics, cost dashboards |
| 15 | [`cba0197`](https://github.com/hamidmatiny/Vulcan/commit/cba0197) | Security hardening, docs site, v1.0.0 release |

### Phase 14 — Observability (tracing, metrics, cost dashboards) — `04beccb`

- `observability/`: Prometheus (:9008), Grafana (:9009), Tempo (:9010), OTel collector, Alertmanager, blackbox
- OTel on gateway + bentoml/ray-serve/triton/vllm; scrapes existing phase-0 `/metrics`
- Cost-exporter reuses benchmark + Bedrock pricing-reference; LIVE vs PLACEHOLDER GPU panels (ADR-002)

### Phase 13 — Routing gateway — `3d83fe3`

- `gateway/` on **:9007**; ADR-006; explainable fallback; SageMaker/KServe excluded without recorded data

### Phase 12 — Kubeflow → KServe — `cf0c480`

- KFP train→eval→register; Training Operator + KServe handoff; validate-only CI

### Phase 11 — Bedrock adapter — `eece3f6`

- `bedrock-gateway/` + static `pricing-reference.json`; moto CI

### Phase 10 — SageMaker — `559203d`

- Pipelines / Registry / Endpoint helpers; moto CI; manual runbook

### Phase 9 — Karpenter + checkpointing — `856277f`

- Spot NodePools; SIGTERM checkpoint library; ADR-005

### Phase 8 — Kueue — `ba466fc`

- Multi-tenant GPU queues; ADR-004

### Phase 7 — GPU Operator / MIG — `c5c4fdf`

- Operator values, MIG profiles, terraform GPU EKS plan-only; ADR-003

### Phase 6 — KServe — `372dc19`

- Helm InferenceServices wrapping Triton/vLLM; validate-only

### Phase 5 — vLLM — `54c5bb0`

- Host **:9004**; LLM-only shim; CPU k6 artifact

### Phase 4 — Triton — `3e35d86`

- Host **:9003** shim + internal engine; ONNX model repo

### Phase 3 — Ray Serve — `181c72c`

- Host **:9002**; both reference models

### Phase 2 — BentoML — `c7f7a02`

- Host ports **9000–9099** convention; **:9000** adapter

### Phase 1 — Models + benchmark — `e8d1e88`

- GPT-2 + ResNet-18 pins; k6 harness; serving/common client + conformance

### Phase 0 — Foundations — `bd92ee4`

- Contract OpenAPI/JSON Schema; ADR-001/002; CI skeleton; CPU compose placeholder
