# Model manifest (byte-identical pins)

Every Vulcan serving backend MUST serve weights whose **sha256** matches this file.
Cross-backend benchmarks are only legitimate when all backends load these pins.

**Generated:** 2026-07-26  
**Pins source:** [`pins.json`](./pins.json)

## Policy

- CI never downloads GPU builds or runs on GPU hardware (ADR-002).
- Weights live under `models/artifacts/` (gitignored binaries); this manifest is committed.
- Re-export with `python models/scripts/export_*.py` then `python models/scripts/write_manifest.py --require-artifacts`.

## Models

### `reference-tiny-llm`

- **Modality:** `llm`
- **Source:** Hugging Face `openai-community/gpt2` @ `607a30d783dfa663caf39e06633721c8d4cfcd7e`
- **Params (approx):** 124M
- **Export format:** `safetensors`
- **Artifact dir:** `artifacts/llm/gpt2-small/`
- **Primary file:** `model.safetensors`
- **Primary sha256:** `248dfc3911869ec493c76e65bf2fcf7f615828b0254c12b473182f0f81d3a707`

| File | sha256 |
|------|--------|
| `config.json` | `0daed7749b4f02b8f76240d5444551d7b08712dab4d0adb8239c56ba823bb7b4` |
| `generation_config.json` | `ed0b32ac72c0f5f44a719abb2d7786ea5146c871f83717b7f2018065954de02b` |
| `merges.txt` | `1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5` |
| `model.safetensors` | `248dfc3911869ec493c76e65bf2fcf7f615828b0254c12b473182f0f81d3a707` |
| `tokenizer.json` | `8414cab924d8b9b33013f0d221c5862f365ee9be39c5c2bfae8a5a9e970478a6` |
| `tokenizer_config.json` | `5e04eb606e3a1583530a42e36c2a6b6615c86f34fe77e44d9ddeb43ff940931f` |
| `vocab.json` | `196139668be63f3b5d6574427317ae82f612a97c5d1cdaf36ed2256dbf636783` |

> GPT-2 small (causal LM). Prefer safetensors for HF/vLLM/Bento paths; ONNX export is optional and not required for the LLM pin.

### `reference-tiny-vision`

- **Modality:** `vision`
- **Source:** torchvision `resnet18` / `ResNet18_Weights.IMAGENET1K_V1`
- **Upstream URL:** `https://download.pytorch.org/models/resnet18-f37072fd.pth`
- **Export format:** `onnx`
- **Artifact dir:** `artifacts/vision/resnet18/`
- **Primary file:** `model.onnx`
- **Primary sha256:** `7b7aa3632a82316840b62325e940c392f1db84b80d0eef30a3c06e0dc303c10f`

| File | sha256 |
|------|--------|
| `imagenet_classes.json` | `47c75d27d7a4c62415c9c1c4536ac98c68e1417b880987dbc5b166c3b7ebf1d9` |
| `model.onnx` | `7b7aa3632a82316840b62325e940c392f1db84b80d0eef30a3c06e0dc303c10f` |
| `preprocess.json` | `f9df32d8b268b1a17b79ea9d35a24beb63bb3dd7a0be0917a10d86138962d49b` |

> ImageNet-pretrained ResNet-18 exported to ONNX for Triton/ONNX Runtime and other backends.

## Verification

```bash
python models/scripts/verify_manifest.py
```
