#!/usr/bin/env python3
"""Export torchvision ResNet-18 (ImageNet) to ONNX for cross-backend vision serving."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

import torch
import torchvision
from torchvision.models import ResNet18_Weights

from common import ARTIFACTS_ROOT, ensure_dir, load_pins, sha256_file, write_sidecar_hashes


def _seed_for_reproducible_onnx() -> None:
    """Stabilize ONNX graph/constant serialization across processes.

    PYTHONHASHSEED must also be set in the process environment *before* the
    interpreter starts (CI top-level env + Makefile models-export). Setting it
    here is defense-in-depth for child libs that re-read the env var.
    """
    os.environ.setdefault("PYTHONHASHSEED", "0")
    random.seed(0)
    torch.manual_seed(0)
    torch.set_num_threads(1)  # avoid nondeterministic reduction order in constant folding


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: models/artifacts/vision/resnet18)",
    )
    args = parser.parse_args()

    _seed_for_reproducible_onnx()

    pins = load_pins()
    spec = pins["models"]["reference-tiny-vision"]
    export = spec["export"]
    source = spec["source"]

    out_dir = args.out or (ARTIFACTS_ROOT / "vision" / "resnet18")
    ensure_dir(out_dir)

    weights = ResNet18_Weights.IMAGENET1K_V1
    print(f"Loading {source['name']} ({source['weights']})", file=sys.stderr)
    model = torchvision.models.resnet18(weights=weights)
    model.eval()

    # Record upstream weight file hash when torchvision caches it.
    weight_url = source["weights_url"]
    torch_hub_dir = Path(torch.hub.get_dir()) / "checkpoints"
    # torchvision stores as resnet18-f37072fd.pth
    upstream_name = Path(weight_url).name
    upstream_path = torch_hub_dir / upstream_name
    upstream_sha = sha256_file(upstream_path) if upstream_path.is_file() else None

    shape = tuple(export["input_shape"])
    dummy = torch.zeros(shape, dtype=torch.float32)
    onnx_path = out_dir / export["primary_file"]
    opset = int(export["opset"])

    print(f"Exporting ONNX opset={opset} → {onnx_path}", file=sys.stderr)
    torch.onnx.export(
        model,
        dummy,
        str(onnx_path),
        input_names=["pixel_values"],
        output_names=["logits"],
        dynamic_axes={
            "pixel_values": {0: "batch"},
            "logits": {0: "batch"},
        },
        opset_version=opset,
        do_constant_folding=True,
    )

    # Sidecar: labels + preprocess so backends share the same contract inputs.
    categories = weights.meta.get("categories") or []
    labels_path = out_dir / "imagenet_classes.json"
    labels_path.write_text(json.dumps(categories, indent=2) + "\n", encoding="utf-8")

    preprocess = {
        "resize": 256,
        "crop": 224,
        "mean": list(weights.meta.get("mean") or [0.485, 0.456, 0.406]),
        "std": list(weights.meta.get("std") or [0.229, 0.224, 0.225]),
        "input_name": "pixel_values",
        "output_name": "logits",
        "input_shape": list(shape),
    }
    (out_dir / "preprocess.json").write_text(json.dumps(preprocess, indent=2) + "\n", encoding="utf-8")

    # Pin only stable runtime artifacts (not the meta sidecar, which embeds these hashes).
    tracked = [
        p
        for p in out_dir.iterdir()
        if p.is_file()
        and p.name not in {"sha256sums.txt", "export-meta.json"}
        and not p.name.startswith(".")
    ]
    hashes = write_sidecar_hashes(out_dir, tracked)
    meta = {
        "model_id": "reference-tiny-vision",
        "source_weights": source["weights"],
        "source_weights_url": weight_url,
        "source_weights_sha256": upstream_sha,
        "format": export["format"],
        "opset": opset,
        "files": hashes,
    }
    (out_dir / "export-meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(meta, indent=2))
    print(f"OK: wrote {onnx_path} sha256={hashes[onnx_path.name]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
