# serving

Contract-compliant model-serving backends. Each subdirectory implements [`contracts/model-contract`](../contracts/model-contract/) exactly and MUST provide a **CPU-only dev mode** ([ADR-002](../docs/adr/002-gpu-cost-safety-policy.md)).

| Backend | Status | Host port |
|---------|--------|-----------|
| [`common/`](./common/) | Client SDK, conformance, reference server | **9001** |
| [`bentoml/`](./bentoml/) | Phase 2 — both reference models, contract-complete | **9000** |
| [`ray-serve/`](./ray-serve/) | Phase 3 — both reference models, contract-complete | **9002** |
| [`triton/`](./triton/) | Phase 4 — both reference models (ONNX + contract shim) | **9003** |
| [`vllm/`](./vllm/) | Phase 5 — **LLM-only** (OpenAI-compatible engine + shim) | **9004** |
| [`kserve/`](./kserve/) | Stub | TBD in 9000–9099 |
