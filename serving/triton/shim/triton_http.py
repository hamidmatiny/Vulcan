"""Minimal Triton HTTP/JSON client (v2 protocol)."""

from __future__ import annotations

from typing import Any

import httpx
import numpy as np

_NP_TO_TRITON = {
    np.dtype("float32"): "FP32",
    np.dtype("float64"): "FP64",
    np.dtype("int32"): "INT32",
    np.dtype("int64"): "INT64",
    np.dtype("bool"): "BOOL",
}


class TritonHttpError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TritonHttpClient:
    def __init__(self, url: str, *, timeout: float = 120.0) -> None:
        base = url if "://" in url else f"http://{url}"
        self._client = httpx.Client(base_url=base.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def is_server_live(self) -> bool:
        return self._client.get("/v2/health/live").status_code == 200

    def is_server_ready(self) -> bool:
        return self._client.get("/v2/health/ready").status_code == 200

    def is_model_ready(self, model_name: str) -> bool:
        return self._client.get(f"/v2/models/{model_name}/ready").status_code == 200

    def infer(
        self,
        model_name: str,
        inputs: dict[str, np.ndarray],
        output_names: list[str],
    ) -> dict[str, np.ndarray]:
        payload_inputs: list[dict[str, Any]] = []
        for name, arr in inputs.items():
            contiguous = np.ascontiguousarray(arr)
            dtype = _NP_TO_TRITON.get(contiguous.dtype)
            if dtype is None:
                raise TritonHttpError(f"unsupported numpy dtype: {contiguous.dtype}")
            payload_inputs.append(
                {
                    "name": name,
                    "shape": list(contiguous.shape),
                    "datatype": dtype,
                    "data": contiguous.reshape(-1).tolist(),
                }
            )
        body = {
            "inputs": payload_inputs,
            "outputs": [{"name": n} for n in output_names],
        }
        resp = self._client.post(f"/v2/models/{model_name}/infer", json=body)
        if resp.status_code != 200:
            raise TritonHttpError(
                f"triton infer failed: {resp.status_code} {resp.text[:500]}",
                status_code=resp.status_code,
            )
        data = resp.json()
        out: dict[str, np.ndarray] = {}
        for item in data.get("outputs") or []:
            name = item["name"]
            shape = item["shape"]
            dtype = item["datatype"]
            flat = item["data"]
            np_dtype = {
                "FP32": np.float32,
                "FP64": np.float64,
                "INT32": np.int32,
                "INT64": np.int64,
                "BOOL": np.bool_,
            }.get(dtype, np.float32)
            out[name] = np.asarray(flat, dtype=np_dtype).reshape(shape)
        return out
