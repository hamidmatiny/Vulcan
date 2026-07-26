# models

Pinned CPU-runnable reference models for Vulcan. Every later serving backend must load **byte-identical** weights so cross-backend benchmarks are legitimate.

## Pins

| Contract `model_id` | Source | Export | Details |
|---------------------|--------|--------|---------|
| `reference-tiny-llm` | Hugging Face `openai-community/gpt2` @ pinned revision (~124M) | `safetensors` | Causal LM for `/v1/infer` `modality=llm` |
| `reference-tiny-vision` | torchvision ResNet-18 ImageNet | `onnx` (opset 17) | Vision classifier for `modality=vision` |

Canonical digests: **[`MANIFEST.md`](./MANIFEST.md)** · machine-readable: [`pins.json`](./pins.json)

## Fetch / export

```bash
make models-export    # downloads + exports under models/artifacts/
make models-verify    # checks sha256 against MANIFEST.md
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
  artifacts/llm/gpt2-small/
  artifacts/vision/resnet18/
```
