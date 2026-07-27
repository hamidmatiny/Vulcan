# ADR 011 — LoRA / PEFT adapter fine-tuning + transparent serving

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 19 (`training/fsdp-ddp/lora/`, `contracts/training-job-contract/` LoRA schemas, `serving/bentoml/` adapter load)

## Context

Parameter-efficient fine-tuning (LoRA / PEFT) is a common production technique: train a small adapter on a pinned base model, then serve base+adapter without changing the client API. Vulcan already has a unified serving contract ([ADR-001](./001-unified-model-serving-contract.md)) and a unified training job contract ([ADR-010](./010-unified-training-job-contract.md)). A new fine-tuning technique must not invent a parallel north-bound surface or a second model registry.

Adapters from short CPU fine-tunes also have run-to-run floating-point variance. [ADR-009](./009-gpu-cost-safety-extends-to-training.md) already forbids SHA256-pinning training checkpoints for that reason; the same rule must apply to adapter weights.

## Decision

1. **North-bound serving contract stays unchanged.** Base+adapter is served through the existing `POST /v1/infer` (and siblings) from ADR-001. Clients do not see PEFT APIs. The adapter-attached variant is a distinct `model_id` (e.g. `reference-tiny-llm-lora-demo`) registered via the existing resource-requirements pattern — not a parallel registry.
2. **Fine-tune job type is contract data.** Add `LoraFineTuneSpec` / `LoraFineTuneResult` alongside `TrainingJobSpec` / `TrainingJobResult` in [`contracts/training-job-contract/`](../../contracts/training-job-contract/) (extends ADR-010). OpenAPI + JSON Schema + tests update together.
3. **One vertical slice only.** Training: HuggingFace `peft` on `training/fsdp-ddp/lora/` (plain PyTorch, no Ray/DeepSpeed). Serving: BentoML only optionally loads base + adapter. Other backends stay untouched in this phase.
4. **Structural verification, not hash pins (extends ADR-009 by name).** Do **not** pin `adapter_model.safetensors` SHA256 in `models/MANIFEST.md`. CI proves the adapter by: schema-valid result, correct rank/shape in `adapter_config.json`, successful load, and a **measurable logits delta** vs. the base model on a fixed prompt (epsilon gate).

## Alternatives considered

| Option | Why not |
|--------|---------|
| Wire LoRA into all training + serving backends | Combinatorial expansion; one slice proves the differentiator |
| New PEFT-native HTTP surface | Breaks ADR-001 north-bound discipline |
| SHA256-pin adapter weights like reference exports | Same FP variance trap ADR-009 already rejected for checkpoints |
| Change `/v1/infer` schema for adapters | Unnecessary; `model_id` already selects the variant |

## Consequences

**Gains**

- PEFT lands without rewriting the serving contract or inventing a second registry.
- ADR-009's structural-verification rule is explicit for adapters before anyone reintroduces hash pins.

**Trade-offs (accepted)**

- Only FSDP/DDP + BentoML in phase 19; other backends can adopt later behind the same contracts.
- Adapter artifacts are CI-generated / local-run outputs — not byte-identical across runs.

## Compliance

- `check-adr-gate.sh` maps `training/fsdp-ddp/lora/**` and LoRA schema paths under `contracts/training-job-contract/` → this ADR, **alongside** existing ADR-009 / ADR-010 mappings for `training/**` (not replacing them).
- CI job is CPU-only (ADR-002 / ADR-009); no new host port.
