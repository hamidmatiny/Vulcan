# checkpointing

**Path:** `autoscaling/checkpointing/`  
**Phase:** 9  
**ADR:** [ADR-005 Spot GPU strategy](../../docs/adr/005-spot-gpu-strategy.md)

## Purpose

Reference implementation of **checkpoint-on-SIGTERM** and **resume-on-restart** for a long-running GPU job. The example workload is the phase-1 `reference-tiny-llm` (GPT-2 small) **fine-tuning path**, stubbed so CI can run without torch or a GPU. Phase 12’s real training Job should reuse this contract (same signals, same `checkpoint.json` shape or an equivalent HF/accelerate adapter).

## Contract

1. On start: if `checkpoint.json` exists, load `step` / `weight_digest` / metadata and continue.
2. Periodically (every N steps) write a checkpoint.
3. On `SIGTERM` / `SIGINT`: flush checkpoint, exit `0` (treat as clean preemption).
4. On restart: resume from last completed step; digest chain must match a continuous run.

```bash
make test-checkpointing
# or
cd autoscaling/checkpointing && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

Demo CLI:

```bash
.venv/bin/vulcan-checkpoint-finetune --checkpoint-dir /tmp/vulcan-ckpt --total-steps 100
# elsewhere: kill -TERM <pid>  →  re-run the same command to resume
```

## Interaction with Kueue preemption (phase 8)

Kueue may preempt a training `Workload` when inference reclaim / higher `WorkloadPriorityClass` needs GPUs ([ADR-004](../../docs/adr/004-multi-tenant-gpu-scheduling-with-kueue.md)). Kubernetes delivers **SIGTERM** to the pod; `terminationGracePeriodSeconds` must be long enough to flush (NodePool sets `terminationGracePeriod: 5m`). Without checkpoint-resume, preempted training restarts from step 0 and wastes GPU time.

## Interaction with Karpenter spot interruption

AWS Spot gives ~**2 minutes** notice; Karpenter cordons/drains and the kubelet sends SIGTERM. This package treats that notice the same as Kueue preemption: checkpoint then exit. Persistent volume (or object storage) for `checkpoint-dir` is required so a replacement pod on a new node can resume.

NodePool disruption budgets ([karpenter/](../karpenter/)) limit **voluntary** consolidation; they do **not** stop AWS reclaiming a spot instance. Checkpointing is the safety net for training; real-time inference should not rely on spot (ADR-005).

## Layout

```text
src/vulcan_checkpointing/   FineTuneJob + CheckpointStore + CLI
tests/                      SIGTERM simulation (no GPU)
```
