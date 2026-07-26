#!/usr/bin/env python3
"""Fetch GPT-2 small (pinned revision) and materialize safetensors for all backends."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

from common import ARTIFACTS_ROOT, ensure_dir, load_pins, write_sidecar_hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: models/artifacts/llm/gpt2-small)",
    )
    args = parser.parse_args()

    pins = load_pins()
    spec = pins["models"]["reference-tiny-llm"]
    source = spec["source"]
    export = spec["export"]

    out_dir = args.out or (ARTIFACTS_ROOT / "llm" / "gpt2-small")
    ensure_dir(out_dir)

    repo_id = source["repo_id"]
    revision = source["revision"]
    print(f"Downloading {repo_id}@{revision} → {out_dir}", file=sys.stderr)

    # Pull the weight + tokenizer/config files backends need for byte-identical loads.
    allow = [
        "model.safetensors",
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.json",
        "merges.txt",
        "generation_config.json",
    ]
    snapshot_download(
        repo_id=repo_id,
        revision=revision,
        allow_patterns=allow,
        local_dir=out_dir,
    )

    # Prefer hub safetensors; if absent, fail clearly (pin must stay on a safetensors revision).
    primary = out_dir / export["primary_file"]
    if not primary.is_file():
        # Some revisions only ship pytorch_model.bin — convert via safetensors if present as bin.
        bin_path = out_dir / "pytorch_model.bin"
        if bin_path.is_file():
            from safetensors.torch import save_file
            import torch

            state = torch.load(bin_path, map_location="cpu", weights_only=True)
            save_file(state, str(primary))
            print(f"Converted {bin_path.name} → {primary.name}", file=sys.stderr)
        else:
            # Last resort: download explicitly
            hf_hub_download(
                repo_id=repo_id,
                revision=revision,
                filename="model.safetensors",
                local_dir=out_dir,
            )

    if not primary.is_file():
        raise SystemExit(f"primary weight missing after download: {primary}")

    tracked = [
        p
        for p in out_dir.iterdir()
        if p.is_file() and p.name != "sha256sums.txt" and not p.name.startswith(".")
    ]
    hashes = write_sidecar_hashes(out_dir, tracked)
    meta = {
        "model_id": "reference-tiny-llm",
        "repo_id": repo_id,
        "revision": revision,
        "format": export["format"],
        "files": hashes,
    }
    (out_dir / "export-meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    print(f"OK: wrote {primary} sha256={hashes[primary.name]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
