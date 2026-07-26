# Changelog

All notable changes to Vulcan are documented here.

## [Unreleased]

### Phase 0 — Foundations

- Monorepo scaffold matching the target layout (`contracts/`, `serving/*`, `gpu-infra/*`, `infra/*`, …)
- `contracts/model-contract`: OpenAPI 3.1 + JSON Schema for `/health`, `/metrics`, `/v1/infer`, resource-requirements
- [ADR-001](./docs/adr/001-unified-model-serving-contract.md) — unified serving contract
- [ADR-002](./docs/adr/002-gpu-cost-safety-policy.md) — GPU cost-safety policy
- GitHub Actions CI skeleton: lint, unit tests (coverage ≥65% on contracts), ADR gate
- Makefile targets: `up`, `down`, `logs`, `test`, `lint`
- `.cursor/rules/vulcan-foundations.mdc` for always-on agent guidance
- Apache-2.0 license, docker-compose (CPU-only placeholder), `.env.example`
