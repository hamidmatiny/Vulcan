# LoRA / PEFT fine-tune (ADR-011)

CPU-only adapter training on pinned `reference-tiny-llm` (GPT-2 small), writing
`adapter_model.safetensors` + `adapter_config.json`.

**Do not SHA256-pin adapter weights** (ADR-009 / ADR-011). Verify structurally:
rank/shape, load, logits delta vs base.

```bash
make models-export   # once
make test-lora-peft
# or:
PYTHONPATH=. python training/fsdp-ddp/lora/train_lora.py \
  --output-dir training/results/lora-demo
```

Served model id (BentoML, unchanged `/v1/infer`): `reference-tiny-llm-lora-demo`.
