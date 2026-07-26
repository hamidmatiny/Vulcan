# Changelog

All notable changes to Vulcan are documented here.

## [Unreleased]

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
