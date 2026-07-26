# serving/ray-serve

Ray Serve adapter that serves **both** phase-1 reference models behind the phase-0 Vulcan model contract.

| Host port | Service |
|-----------|---------|
| **9002** | This backend (`VULCAN_RAY_SERVE_PORT`) |

Vulcan host ports are **9000–9099** (see `.cursor/rules` and root `docker-compose.yml`).

## Ray Serve vs Ray Core (do not conflate)

| | **Ray Serve** (this directory) | **Ray Core** (elsewhere, e.g. Argus ingestion) |
|--|--------------------------------|--------------------------------------------------|
| **Job** | **Inference-time** HTTP serving: deployments, replicas, request routing, autoscaling of model workers | **Data-/task-plane** parallelism: tasks, actors, Dataset pipelines for ingest/ETL |
| **Unit** | `Deployment` + optional ingress (FastAPI) exposing stable HTTP routes | Remote functions / actors processing streams or batches |
| **Scaling knob** | `num_replicas`, `max_ongoing_requests`, GPU/CPU per replica | Task concurrency, actor pools, cluster workers for throughput of jobs |
| **When it runs** | Online path: every `/v1/infer` | Offline/nearline path: simulators, consumers, transforms |

**Vulcan uses Ray Serve here only for model serving.** Sibling projects (and any future Vulcan ingest) may use **Ray Core** for pipelines — that is a different product surface. Sharing the “Ray” brand does **not** mean this adapter reuses Argus ingestion actors or Dataset APIs.

```text
Client → contract routes (FastAPI @serve.ingress)
              ↓
     VulcanRayService (Ray Serve Deployment, N replicas)
              ↓
  GPT-2 (transformers) + ResNet-18 (ONNX Runtime)
```

## Deployment / replica model → contract mapping

Ray Serve wraps a class in `@serve.deployment` (replica pool) and optionally `@serve.ingress` (HTTP). We mount the **exact** Vulcan contract on that ingress so clients never speak Ray-native APIs (ADR-001).

| Contract | Implementation |
|----------|----------------|
| `GET /health` | Ready when both models loaded in the replica; `backend=ray-serve` |
| `GET /metrics` | Prometheus via `prometheus_client` (`vulcan_infer_*`) |
| `POST /v1/infer` | `llm` → GPT-2; `vision` → ResNet-18 ONNX |
| `GET /v1/resources` | [`resource-requirements.json`](./resource-requirements.json) |

`model_id` values match phase-1 pins: `reference-tiny-llm`, `reference-tiny-vision`.

CPU-dev defaults: `num_replicas=1`, `num_cpus=1` per replica. Scale replicas for load tests; do not confuse that with Ray Core task fan-out.

## Resource-requirements (CPU-dev)

| Field | Value |
|-------|-------|
| `gpu_memory_mib` | min/max **0** |
| `supports_mig` | `false` |
| `supports_quantization` | `true` |
| `cold_start_seconds` | 10–90 (Ray + model load) |
| `cpu_dev_mode` | **`true`** |

## Local run

```bash
make models-export
make up                      # bentoml :9000 + ray-serve :9002
curl -s localhost:9002/health
VULCAN_BACKEND_URL=http://127.0.0.1:9002 make test-serving-common
make benchmark-ray-serve     # → benchmark/results/ray-serve-cpu.json
```

Docker-only:

```bash
docker build -f serving/ray-serve/Dockerfile -t vulcan-ray-serve:cpu .
docker run --rm -p 9002:9002 vulcan-ray-serve:cpu
```

## GPU deployment (manual — not CI)

Per [ADR-002](../../docs/adr/002-gpu-cost-safety-policy.md), CI never runs GPU Ray. See [`serve-config.gpu.yaml`](./serve-config.gpu.yaml) (`num_gpus: 1`). Record real GPU numbers under `docs/benchmarks/`.
