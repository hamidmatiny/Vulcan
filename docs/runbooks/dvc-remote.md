# DVC local remote (manual cloud only)

Vulcan's DVC default remote is a **local filesystem** directory (`.dvc-remote/` in
dev, or a CI temp path). This matches ADR-012: no cloud bucket secrets in CI.

## Production (manual)

Point the same remote name at object storage when operating outside CI:

```bash
# Examples only — do not commit credentials or apply from CI.
dvc remote modify local url s3://YOUR_BUCKET/vulcan-dvc
# or: dvc remote modify local url gs://YOUR_BUCKET/vulcan-dvc
dvc push
dvc pull
```

Same spirit as GPU benchmarks under `docs/benchmarks/`: real cloud remotes are
**manual ops**, never fabricated or applied by automation.

## Scope reminder

DVC tracks **only** deterministic reference exports (`gpt2-small` / `resnet18`
primaries). Training checkpoints and LoRA adapters stay out of DVC (ADR-009 /
ADR-011 / ADR-012).
