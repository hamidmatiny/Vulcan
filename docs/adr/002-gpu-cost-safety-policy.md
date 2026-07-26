# ADR 002 — GPU cost-safety policy

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 0+ (all phases)

## Context

Vulcan’s product surface is GPU orchestration and multi-backend model serving. Accidental CI or automation against real GPU nodes (cloud spot/on-demand, local discrete GPUs billed via cloud agents, or cluster apply of GPU Operator / Karpenter NodePools) can burn budget quickly and is hard to reverse mid-PR.

Sibling project Argus already treats production-shaped infra as **validate-in-CI, apply-out-of-band**. Vulcan must be stricter: GPUs are the expensive resource class.

## Decision

### CI and automation (hard rules)

1. **CI never provisions or runs against real GPU hardware or cloud GPU nodes.**
2. **All serving backends must provide a CPU-only dev mode** against a small reference model (`models/` + `cpu_dev_mode: true` in the resource manifest).
3. **GPU infra manifests are validated but never applied by automation:**
   - Terraform: `terraform validate` / `terraform plan` only — never `apply` in GitHub Actions.
   - Helm: `helm template` + kubeconform (and similar) — never `helm upgrade --install` in CI.
   - Policy: conftest / OPA checks against rendered manifests.
4. **Real GPU benchmark runs are manual** and documented under [`docs/benchmarks/`](../benchmarks/). Results may be checked in; the jobs that produce them are not.

### Local development

- `make up` / `docker-compose.yml` bring up CPU-only paths by default.
- Selecting GPU runtime mode requires an explicit, non-default local override and must never be the CI matrix default.

### Package gate

- Artifacts with `cpu_dev_mode: false` are excluded from CI test matrices and compose profiles used by automation.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Nightly GPU CI on a small cloud node | Still recurring spend; flake + quota risk; easy to expand accidentally |
| “Plan-only except main” apply | Merge-to-main apply still surprises cost owners; violates explicit manual gate |
| Mock-only (no CPU reference model) | Misses real serving adapter bugs that CPU reference models catch cheaply |

## Consequences

**Gains**

- Predictable CI cost; no surprise GPU invoices from PRs.
- Developers can iterate on contracts/adapters on laptops without NVIDIA hardware.
- Infra PRs still get structural validation (plan/template/conftest).

**Trade-offs (accepted)**

- GPU-specific performance regressions are **not** caught in CI — they require manual runs recorded in `docs/benchmarks/`.
- Some CUDA/MIG edge cases only appear on real hardware; adapters must isolate those behind feature flags.
- Contributors need discipline: never “just add” a self-hosted GPU runner to the default workflow.

## Compliance checklist (reviewers)

- [ ] No workflow step launches EC2/GKE/EKS GPU node groups or calls cloud APIs that create them.
- [ ] No `terraform apply`, `helm upgrade`, `kubectl apply` against GPU-operator / MIG / Karpenter GPU pools in Actions.
- [ ] Serving changes include or preserve CPU-dev mode + reference model path.
- [ ] Benchmark claims cite `docs/benchmarks/` (manual), not CI green checks.
