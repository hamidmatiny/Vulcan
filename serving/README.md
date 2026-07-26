# serving

Contract-compliant model-serving backends. Each subdirectory implements [`contracts/model-contract`](../contracts/model-contract/) exactly and MUST provide a **CPU-only dev mode** ([ADR-002](../docs/adr/002-gpu-cost-safety-policy.md)).

| Backend | Status |
|---------|--------|
| [`common/`](./common/) | Shared helpers (phase 0 stub) |
| [`bentoml/`](./bentoml/) | Phase 0 stub |
| [`ray-serve/`](./ray-serve/) | Phase 0 stub |
| [`triton/`](./triton/) | Phase 0 stub |
| [`vllm/`](./vllm/) | Phase 0 stub |
| [`kserve/`](./kserve/) | Phase 0 stub |
