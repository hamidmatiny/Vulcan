# Triton GPU / TensorRT path (manual — not CI)

Per [ADR-002](../../../docs/adr/002-gpu-cost-safety-policy.md), Vulcan CI and `make up` never provision GPUs. Use this path on a CUDA host when you want TensorRT acceleration.

## 1. Switch `instance_group` to GPU

In each model's `config.pbtxt`, replace the CPU instance group:

```protobuf
instance_group [
  {
    count: 1
    kind: KIND_GPU
    gpus: [ 0 ]
  }
]
```

## 2. Enable TensorRT optimization (ONNX → TensorRT EP)

```protobuf
optimization {
  execution_accelerators {
    gpu_execution_accelerator : [ {
      name : "tensorrt"
      parameters { key: "precision_mode" value: "FP16" }
      parameters { key: "max_workspace_size_bytes" value: "1073741824" }
    } ]
  }
}
```

Keep `platform: "onnxruntime_onnx"` (TensorRT as an ONNX Runtime execution provider) or use Triton’s dedicated TensorRT backend after an offline plan build — both are valid; document which plan you used under `docs/benchmarks/`.

## 3. Run the official GPU image

```bash
docker run --gpus all --rm \
  -v "$PWD/serving/triton/model_repository:/models" \
  -p 8000:8000 -p 8001:8001 -p 8002:8002 \
  nvcr.io/nvidia/tritonserver:24.05-py3 \
  tritonserver --model-repository=/models
```

Point the contract shim at that server (`TRITON_URL=host.docker.internal:8000` or compose override) with `VULCAN_RUNTIME_MODE=gpu`.

## 4. Record results

Save GPU numbers under [`docs/benchmarks/`](../../../docs/benchmarks/) — never treat CI CPU k6 (`triton-cpu.json`) as a GPU perf claim.
