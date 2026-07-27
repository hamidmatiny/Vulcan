# Case study — Vulcan for a technical hiring audience

Vulcan is a **multi-backend model-serving platform** with a single north-bound HTTP contract, a benchmark-driven router, GPU-cluster IaC that CI validates but never applies, and observability wired to the same contract metrics every adapter already exposes.

## What is CPU-mode by default (cost safety)

Per [ADR-002](adr/002-gpu-cost-safety-policy.md), automation **never** provisions or runs real GPU hardware:

| Area | What CI / `make up` actually does |
|------|-----------------------------------|
| Serving adapters (bentoml, ray-serve, triton, vllm) | CPU Docker images + short k6 → `benchmark/results/*-cpu.json` |
| Gateway | Routes using those recorded JSON files + Bedrock `pricing-reference.json` ([ADR-006](adr/006-routing-policy.md)) |
| Observability | Scrapes `/metrics`, blackbox `/health`, OTel→Tempo; GPU dashboard series are **explicit placeholders** |
| SageMaker / Bedrock | moto / fake credentials — no live AWS spend |
| KServe, GPU Operator, MIG, Kueue, Karpenter, Kubeflow | `helm template` / `terraform validate|plan` / conftest — **no apply** |

The contract itself ([ADR-001](adr/001-unified-model-serving-contract.md)) is real and enforced: every adapter and the gateway speak `/health`, `/metrics`, `/v1/infer`, `/v1/resources`.

## What is real infra-as-code ready for a GPU cluster

These trees are written as deployable artifacts, not slides:

- **MIG strategy** — [ADR-003](adr/003-mig-partitioning-strategy.md) + `gpu-infra/mig/`
- **Multi-tenant GPU scheduling** — [ADR-004](adr/004-multi-tenant-gpu-scheduling-with-kueue.md) + `gpu-infra/kueue/`
- **Spot / checkpoint resume** — [ADR-005](adr/005-spot-gpu-strategy.md) + `autoscaling/karpenter/` + `autoscaling/checkpointing/`
- **EKS GPU node groups** — `infra/terraform/environments/gpu-eks/` (plan-only in CI)
- **KServe packaging** — `serving/kserve/helm/` wrapping the same contract images
- **Training→serving loop** — `pipelines/kubeflow/` compiling to KServe handoff manifests

“Ready” here means: labels/taints/quotas/profiles match across Terraform, Helm, and ADRs, and CI would fail if those contracts drifted — not that a GPU node was rented in GitHub Actions.

## Evidence over slogans

| Claim | Evidence in-repo |
|-------|------------------|
| One API for every backend | ADR-001 + `contracts/model-contract` + conformance suite |
| No silent GPU burn in CI | ADR-002 + compose `VULCAN_RUNTIME_MODE=cpu` + validate-only infra jobs |
| Routing is explainable | ADR-006 + `routing` object on infer responses + `gateway/scripts/ci_fallback.sh` |
| Cost panels reuse router data | `observability/cost-exporter` reads the same benchmark/pricing files as `gateway/internal/catalog` |
| Coverage bar | `COVERAGE_MIN=65` on gated Python packages + `gateway/internal` Go coverage |

## How to judge the work in an interview

1. Read ADR-001 and ADR-002 first — they constrain every later phase.
2. Run [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) on a laptop (CPU only).
3. Skim [`KNOWN_GAPS.md`](KNOWN_GAPS.md) for what is simulated vs cluster-ready.
4. Ask for a GPU-budget follow-up: the next work is apply + measure, not inventing another adapter API.
