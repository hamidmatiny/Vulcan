# ADR 012 — Data versioning with DVC (deterministic model exports only)

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 20 (`dvc.yaml`, `.dvc/`, `models/scripts/verify_dvc_manifest.py`)

## Context

The v1.1.0 CI saga was, at bottom, a **manual artifact-versioning** problem: [`models/MANIFEST.md`](../../models/MANIFEST.md) + per-artifact `sha256sums.txt` are hand-maintained pins, and the vision ONNX export was not byte-reproducible until phase 18 forced `PYTHONHASHSEED=0` / single-threaded export / CPU torch. That pain is real; this ADR adopts the standard tool (DVC) for the same job — not a bolted-on technology for its own sake.

[ADR-009](./009-gpu-cost-safety-extends-to-training.md) already forbids content-hash pins for training checkpoints. [ADR-011](./011-lora-peft-adapter-serving-integration.md) extended that rule to LoRA adapters. This is the **third** explicit drawing of the same boundary: floating-point training/adapter outputs must not be DVC-tracked by content hash.

## Decision

1. **Adopt DVC for deterministic reference exports only.** Pipeline stages in [`dvc.yaml`](../../dvc.yaml) wrap the existing [`export_llm.py`](../../models/scripts/export_llm.py) / [`export_vision.py`](../../models/scripts/export_vision.py) (no script rewrite). Tracked outs are the primary pin files under `models/artifacts/llm/gpt2-small/` and `models/artifacts/vision/resnet18/`.
2. **Scope boundary (extends ADR-009 / ADR-011 by name).** Do **not** DVC-track `training/results/**`, LoRA adapters, or any non-deterministic training artifact. Those remain CI-uploaded / structurally verified.
3. **Local filesystem remote in CI/dev.** Default remote is gitignored `.dvc-remote/` (or a CI temp path). Production may point the same remote name at S3/GCS — documented in the runbook; not fabricated or applied in CI (same spirit as GPU benchmarks).
4. **Cross-validate, do not replace MANIFEST.** `MANIFEST.md` + `sha256sums.txt` + `verify_manifest.py` stay the human-readable / existing-job source of truth. CI runs a check that SHA256 of each DVC-tracked primary out matches `sha256sums.txt` (and thus MANIFEST), so the two systems cannot silently drift.
5. **Reproducibility proof.** A `dvc-repro` CI job runs `dvc repro` (with the same `PYTHONHASHSEED=0` / CPU torch contract as `make models-export`) and asserts `dvc status` is clean **and** `dvc.lock` is unchanged vs the committed lock — proving phase 18's reproducibility fix under a real versioning tool.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Replace MANIFEST with DVC only | Other jobs already depend on `verify_manifest.py`; ripping it out is churn without gain |
| DVC-track training/adapter dirs | Reintroduces flaky content-hash pins (ADR-009 / ADR-011) |
| Wire a real S3/GCS remote in CI | Secrets + cost; violates "validate locally, apply manually" for non-CPU infra |
| Rewrite export scripts as DVC Python stages | Unnecessary; wrap what already works |

## Consequences

**Gains**

- Artifact versioning is a standard tool with a lockfile, not only a markdown table.
- CI proves byte-stable exports under `dvc repro`, not only ad hoc pytest.

**Trade-offs (accepted)**

- Two systems (DVC + MANIFEST) must stay in sync via the cross-check — intentional redundancy.
- Cloud remotes stay out-of-band documentation until a later ops phase.

## Compliance

- `check-adr-gate.sh` maps `dvc.yaml`, `dvc.lock`, `.dvc/**`, and `models/scripts/*dvc*` → this ADR.
- Never add training/adapter paths as DVC `outs`.
