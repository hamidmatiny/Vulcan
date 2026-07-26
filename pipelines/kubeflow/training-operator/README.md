# Kubeflow Training Operator — PyTorchJob (phase 12)

**Path:** `pipelines/kubeflow/training-operator/`

## Composition callout (phases 7–9)

This manifest is the **actual cluster training step** for `reference-tiny-llm`. It deliberately wires into existing Vulcan GPU control planes instead of defining a parallel queue or node pool:

1. **Kueue (phase 8)** — `kueue.x-k8s.io/queue-name: lq-training` and priority `vulcan-training` (see `gpu-infra/kueue/`).
2. **Karpenter (phase 9)** — `nodeSelector` for `vulcan.dev/gpu-pool=mig-large` / `vulcan.dev/mig=training-large-batch` (NodePool `vulcan-gpu-mig-large`, spot-first per ADR-005).
3. **Checkpoint-resume (phase 9)** — container command `vulcan-checkpoint-finetune` from `autoscaling/checkpointing/`, PVC at `/checkpoints`, `terminationGracePeriodSeconds: 120` for spot SIGTERM.

MIG resource request `nvidia.com/mig-3g.40gb` matches ADR-003 `training-large-batch` / Kueue flavor `mig-large`.

## Validate

```bash
make validate-kubeflow
```

## Apply

Manual only — [runbook](../../../docs/runbooks/kubeflow-local-kind.md). Never from GitHub Actions.
