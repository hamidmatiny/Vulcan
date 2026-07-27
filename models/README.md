# models

Pinned CPU-runnable reference models for Vulcan. Every later serving backend must load **byte-identical** weights so cross-backend benchmarks are legitimate.

## Pins

| Contract `model_id` | Source | Export | Details |
|---------------------|--------|--------|---------|
| `reference-tiny-llm` | Hugging Face `openai-community/gpt2` @ pinned revision (~124M) | `safetensors` | Causal LM for `/v1/infer` `modality=llm` |
| `reference-tiny-vision` | torchvision ResNet-18 ImageNet | `onnx` (opset 17) | Vision classifier for `modality=vision` |

Canonical digests: **[`MANIFEST.md`](./MANIFEST.md)** · machine-readable: [`pins.json`](./pins.json)

DVC (ADR-012) wraps the same export scripts for deterministic outs only — see repo-root
[`dvc.yaml`](../dvc.yaml). `make dvc-repro` runs `dvc repro`, asserts a clean `dvc status`,
and cross-checks primary SHA256s against `sha256sums.txt` / MANIFEST. Training/adapter
artifacts are **not** DVC-tracked. Cloud remotes: [runbook](../docs/runbooks/dvc-remote.md).

## Fetch / export

```bash
make models-export    # downloads + exports under models/artifacts/
make models-verify    # checks sha256 against MANIFEST.md
make dvc-repro        # DVC pipeline + clean status + MANIFEST cross-check
```

Weight binaries (`*.safetensors`, `*.onnx`, …) are gitignored. Config/tokenizer sidecars and `sha256sums.txt` may be committed. CI never requires GPU (ADR-002).

## Layout

```text
models/
  MANIFEST.md
  pins.json
  scripts/export_llm.py
  scripts/export_vision.py
  scripts/write_manifest.py
  scripts/verify_manifest.py
  scripts/verify_dvc_manifest.py
  scripts/requirements-dvc.txt
  artifacts/llm/gpt2-small/
  artifacts/vision/resnet18/
```
