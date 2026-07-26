# serving/common

Shared serving helpers: **thin Python client SDK**, **contract-conformance pytest suite**, and a **trivial reference server** used to prove the harnesses (phase-1).

## Client SDK

```python
from vulcan_serving_common import VulcanClient

with VulcanClient("http://127.0.0.1:8080") as client:
    print(client.health())
    print(client.infer_llm(
        model_id="reference-tiny-llm",
        messages=[{"role": "user", "content": "hi"}],
    ))
```

## Conformance suite

Point any contract-compliant backend at the suite:

```bash
export VULCAN_BACKEND_URL=http://127.0.0.1:8080
make test-serving-common
```

If `VULCAN_BACKEND_URL` is unset, tests auto-start the trivial reference server.

## Reference server

CPU-only stub that implements the phase-0 OpenAPI contract **without loading weights** (ADR-002). Used to green the conformance + k6 harnesses before real backends land.

```bash
make reference-server
# → http://127.0.0.1:8080/{health,metrics,v1/infer,v1/resources}
```

## Layout

| Path | Role |
|------|------|
| `src/vulcan_serving_common/client.py` | Uniform HTTP client |
| `src/vulcan_serving_common/reference_server.py` | Trivial contract server |
| `tests/conformance/` | Schema / health / metrics / error-code checks |
