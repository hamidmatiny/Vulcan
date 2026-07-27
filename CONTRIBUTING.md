# Contributing to Vulcan

Thanks for helping build Vulcan. This repository is developed in **explicit phases** so each layer stays reviewable and production-shaped — same engineering bar as Argus.

## Commit messages

Every commit MUST use one of:

```text
phase-N: <summary>
fix(<component>): <summary>
```

Examples: `phase-0: foundations, model contract, and CI skeleton`, `fix(triton): wait for health before conformance`.

Ad hoc subjects are not allowed. If a change spans phases, prefer splitting PRs; if inseparable, use the **lowest** phase the change primarily advances.

## Before you open a PR

1. Read [ARCHITECTURE.md](./ARCHITECTURE.md) and the component `README.md` you touch.
2. Follow [`.cursor/rules/`](./.cursor/rules/) (always-on foundations).
3. Serving backends must implement [`contracts/model-contract`](./contracts/model-contract/) exactly ([ADR-001](./docs/adr/001-unified-model-serving-contract.md)).
4. Preserve **CPU-only dev mode**; never add CI steps that provision or run real GPUs ([ADR-002](./docs/adr/002-gpu-cost-safety-policy.md)).
5. Architectural choices → new/updated ADR under `docs/adr/`, linked from `docs/adr/index.md`.
6. Coverage for gated packages **≥ 65%** (CI `COVERAGE_MIN`). See table below.
7. Run `make lint` and `make test`. Use `make up` / `make down` if you touch compose.
8. Update `.env.example` when you introduce new configuration.
9. Do not commit secrets, credentials, or production model weights with licenses that forbid redistribution.
10. Docs site: `make docs-build` (MkDocs Material). Prefer snipping existing READMEs over duplicating prose.

## Coverage gate (gated packages)

| Package | Gate |
|---------|------|
| `contracts/model-contract` | pytest-cov ≥65% |
| `serving/common` | pytest-cov ≥65% (unit path; conformance against a live URL skips local cov) |
| `autoscaling/checkpointing` | pytest-cov ≥65% |
| `pipelines/sagemaker` | pytest-cov ≥65% |
| `bedrock-gateway` | pytest-cov ≥65% |
| `pipelines/kubeflow/pipelines` (`vulcan_kfp`) | pytest-cov ≥65% (omits KFP component bodies executed in-cluster) |
| `gateway/internal` | `go test ./internal/...` total ≥65% (`cmd/gateway` thin main excluded) |
| `observability/cost-exporter` | pytest-cov ≥65% |

**Not unit-gated (documented reason):** serving adapters (bentoml/ray/triton/vllm) — contract **conformance + k6** in CI instead of line coverage; Helm/Terraform/KServe charts — validate-only (ADR-002); third-party compose images — not Vulcan packages.

## Definition of done — every new service

1. `README.md` — purpose, how to run, env vars
2. Implements the model contract when it is a serving backend
3. CPU-dev mode + reference model path (serving)
4. Health + Prometheus metrics endpoints
5. Structured logging
6. Tests with coverage ≥ 65% for gated packages
7. Dockerfile when the component is runnable

## ADR gate

CI fails if changes land under `contracts/`, `gpu-infra/`, `autoscaling/`, or `gateway/` without evidence of ADR coverage (see `.github/scripts/check-adr-gate.sh`). When in doubt, add or update an ADR in the same PR.

## Local commands

| Target | Action |
|--------|--------|
| `make up` | Start local compose stack (CPU-only) |
| `make down` | Stop compose stack |
| `make logs` | Follow compose logs |
| `make test` | Run unit tests |
| `make lint` | Run linters |
