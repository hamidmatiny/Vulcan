# ADR 013 — Pluggable experiment tracking (MLflow + W&B offline)

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 21 (`training/common/tracking.py`, compose MLflow on **:9014**)

## Context

Training jobs already compute loss curves and throughput into `TrainingJobResult` /
`metrics.json` (ADR-010). Operators also want those numbers in an experiment UI.
Sprinkling `mlflow.log_metric()` (or W&B calls) through every backend would couple
training code to a vendor SDK — the opposite of the contract-first pattern already
used for serving ([ADR-001](./001-unified-model-serving-contract.md)) and training
jobs ([ADR-010](./010-unified-training-job-contract.md)).

A different landmine than phases 18–20 (hash-pinning): **CI must never call
wandb.ai.** Vulcan already solves this shape of problem for cloud SDKs —
SageMaker and Bedrock tests use **moto** / fake credentials, never live AWS
(`pipelines/sagemaker/`, `bedrock-gateway/`). W&B gets the same discipline:
offline mode only in CI and documented local defaults.

## Decision

1. **One small tracker interface** in [`training/common/tracking.py`](../../training/common/tracking.py):
   `start_run`, `log_params`, `log_metrics`, `log_artifact`, `end_run`. Third
   application of contract-first design (serving contract → training-job contract →
   tracking interface).
2. **Implementations:** `MlflowTracker` (self-hosted MLflow tracking server) and
   `WandbTracker` (**`WANDB_MODE=offline` only**). Selection via
   `VULCAN_TRACKER_BACKEND` ∈ `{mlflow, wandb, none}`; default **`none`** so
   existing jobs are unchanged unless opted in.
3. **MLflow is the self-hosted default UI.** Compose service on host port **9014**
   (`VULCAN_MLFLOW_PORT`), built from [`training/common/Dockerfile.mlflow`](../../training/common/Dockerfile.mlflow)
   (pip-pinned MLflow on `python:3.12-slim` — avoids authenticated `ghcr.io/mlflow`
   pulls). Sqlite file store under gitignored `.mlflow/`; server runs with
   `--serve-artifacts` so host clients can upload without sharing the container
   path. No SaaS account. Register the port in foundations, `.env.example`,
   compose, and CI port-grep (same four-place rule as 9011–9013).
4. **W&B offline-only policy (cite SageMaker/Bedrock moto).** No `WANDB_API_KEY` in
   the repo or CI. CI and local defaults set `WANDB_MODE=offline`. Assertions
   inspect `./wandb/offline-run-*` (or `WANDB_DIR`), never a live dashboard fetch.
5. **Wire-through, don't recompute.** `training/fsdp-ddp` (including LoRA) reports
   existing loss / throughput metrics through the interface — no parallel metric math.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Vendor calls inlined in each `train.py` | N×N coupling; breaks the contract-first habit |
| W&B online mode in CI | Live network + secrets; violates existing moto offline pattern |
| Require tracking always-on | Breaks default CPU jobs and unit tests that need no deps |
| Only MLflow | Fine as default UI, but a second backend proves the interface is real |

## Consequences

**Gains**

- Experiment UIs stay swappable; training backends stay backend-agnostic.
- CI proves metrics landed (MLflow API query + W&B offline dir), not just exit 0.

**Trade-offs (accepted)**

- Optional deps (`mlflow`, `wandb`) only required when a backend is selected.
- Live W&B cloud sync remains a manual ops choice outside this ADR's defaults.

## Compliance

- `check-adr-gate.sh` maps `training/common/tracking*`, MLflow compose/service paths,
  and this ADR file → ADR-013.
- Host port **9014** must appear in all four registration places.
- Never add `WANDB_API_KEY` to CI secrets or `.env.example` as a required field.
