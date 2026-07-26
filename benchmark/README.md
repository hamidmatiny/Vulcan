# benchmark

> Phase 0 stub — implementation lands in a later phase.

**Path:** `benchmark/`

## Purpose

Latency/throughput harnesses for contract-compliant backends (CPU local; GPU runs are manual).

## Status

Scaffolded in **phase-0**. No runtime yet.

## How to run

Not applicable until this component is implemented.

## Contract / policy notes

- Serving backends must implement [`contracts/model-contract`](../contracts/model-contract/) exactly ([ADR-001](../docs/adr/001-unified-model-serving-contract.md)).
- CI never provisions or runs against real GPU hardware ([ADR-002](../docs/adr/002-gpu-cost-safety-policy.md)).
- Coverage gate for gated packages: **≥ 65%** (see root `CONTRIBUTING.md` and CI).
