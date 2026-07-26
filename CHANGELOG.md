# Changelog

All notable changes to Vulcan are documented here.

## [Unreleased]

### Phase 11 — Bedrock-aware gateway adapter

- `bedrock-gateway/`: thin LLM-branch contract shim over Bedrock `InvokeModel` (vLLM-shaped; vision unsupported)
- Static `pricing-reference.json` ($/1K tokens + typical latency) for the phase-13 router
- moto/fake-credential pytest in CI; optional local `:9006` (no compose)

### Phase 10 — SageMaker Pipelines, Endpoints, and Model Registry

- `pipelines/sagemaker/`: SageMaker SDK Pipeline (train → evaluate → register) for `reference-tiny-llm`
- Model Registry + real-time Endpoint deploy/invoke helpers; contract-vocabulary README mapping
- moto-backed pytest in CI (no live AWS); manual runbook with cost notes
- Lint job ADR list includes ADR-005 (kept in sync with adr-gate)

### Phase 9 — Karpenter GPU autoscaling and checkpoint-resume

- `autoscaling/karpenter/`: NodePools/EC2NodeClass (spot + on-demand) wired to phase 7–8 labels
- `autoscaling/checkpointing/`: SIGTERM checkpoint/resume for GPT-2 fine-tune path
- [ADR-005](./docs/adr/005-spot-gpu-strategy.md); adr-gate for `autoscaling/**`

### Phase 8 — Kueue multi-tenant GPU scheduling

- `gpu-infra/kueue/`: inference + training ClusterQueues/LocalQueues, MIG-aware quotas, WorkloadPriorityClasses
- Example Workloads for KServe InferenceService + forward-ref training Job
- [ADR-004](./docs/adr/004-multi-tenant-gpu-scheduling-with-kueue.md); adr-gate requires it for `gpu-infra/kueue/`

### Phase 7 — GPU Operator, device plugin, and MIG

- `gpu-infra/gpu-operator/`: EKS Helm values with explicit driver/toolkit vs device-plugin separation
- `gpu-infra/mig/`: `many-small-inference` + `training-large-batch` profiles; [ADR-003](./docs/adr/003-mig-partitioning-strategy.md)
- `infra/terraform/environments/gpu-eks/`: GPU node groups (labels/taints/instance types); validate/plan only
- CI: path-filtered terraform + helm template + conftest (no apply — ADR-002)

### Phase 6 — KServe adapter

- `serving/kserve/helm/`: InferenceServices wrapping Triton + vLLM contract images (CPU-dev); canary `trafficPercent` example
- CI: path-filtered `helm template` + kubeconform + conftest (no compose, no apply — ADR-002)
- Runbook: [`docs/runbooks/kserve-local-kind.md`](./docs/runbooks/kserve-local-kind.md)

### Phase 5 — vLLM adapter

- Host port **9004** for `serving/vllm` (LLM-only; vision → `unsupported_modality`)
- CPU OpenAI-compatible small-model path + GPU `vllm serve` docs (PagedAttention / continuous batching / TP)
- Compose `vllm` / `vllm-engine`; CI conformance (`VULCAN_CONFORMANCE_MODALITIES=llm`) + k6 → `benchmark/results/vllm-cpu.json`
- Standing commit-message rule: `phase-N:` or `fix(<component>):` only

### Phase 4 — Triton adapter

- Host port **9003** reserved for `serving/triton` (contract shim); Triton engine stays internal
- Triton model repository + ONNX for both phase-1 reference models; CPU `config.pbtxt` + GPU/TensorRT docs
- Compose `triton` / `triton-engine`; CI conformance + short CPU k6 → `benchmark/results/triton-cpu.json`

### Phase 3 — Ray Serve adapter

- `serving/ray-serve/` on host port **9002**: contract-compliant Ray Serve deployments for both phase-1 reference models
- README contrasts **Ray Serve** (inference replicas) vs **Ray Core** (ingest/task plane elsewhere)
- CPU Dockerfile + compose; GPU `serve-config.gpu.yaml` documented, not CI; conformance + short k6 → `benchmark/results/ray-serve-cpu.json`

### Phase 2 — BentoML adapter

- Host port convention **9000–9099** (documented in `.cursor/rules` + `docker-compose.yml`)
- `serving/bentoml/`: contract-compliant BentoML service for both phase-1 reference models (CPU Dockerfile; GPU Bento documented, not CI)
- Compose `bentoml` on `:9000`; CI conformance + short CPU k6 → `benchmark/results/bentoml-cpu.json`

### Phase 1 — Reference models and benchmark harness

- `models/`: fetch/export scripts for GPT-2 small (safetensors) + ResNet-18 (ONNX); [`MANIFEST.md`](./models/MANIFEST.md) pins revisions and sha256 digests
- `serving/common/`: `VulcanClient` SDK, contract-conformance pytest suite, trivial CPU reference server
- `benchmark/`: k6 load harness (parameterized URL/modality/VUs/duration), `results/schema.json`, `compare_results.py` markdown table

### Phase 0 — Foundations

- Monorepo scaffold matching the target layout (`contracts/`, `serving/*`, `gpu-infra/*`, `infra/*`, …)
- `contracts/model-contract`: OpenAPI 3.1 + JSON Schema for `/health`, `/metrics`, `/v1/infer`, resource-requirements
- [ADR-001](./docs/adr/001-unified-model-serving-contract.md) — unified serving contract
- [ADR-002](./docs/adr/002-gpu-cost-safety-policy.md) — GPU cost-safety policy
- GitHub Actions CI skeleton: lint, unit tests (coverage ≥65% on contracts), ADR gate
- Makefile targets: `up`, `down`, `logs`, `test`, `lint`
- `.cursor/rules/vulcan-foundations.mdc` for always-on agent guidance
- Apache-2.0 license, docker-compose (CPU-only placeholder), `.env.example`
