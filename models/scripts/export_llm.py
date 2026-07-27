#!/usr/bin/env python3
"""Fetch GPT-2 small (pinned revision) and materialize safetensors for all backends."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import time

from huggingface_hub import hf_hub_download, snapshot_download
from huggingface_hub.errors import HfHubHTTPError, LocalEntryNotFoundError

from common import ARTIFACTS_ROOT, ensure_dir, load_pins, write_sidecar_hashes


def _with_hub_retries(fn, *, attempts: int = 8, label: str) -> None:
    """Retry Hub calls on 429/5xx; parallel CI jobs share an unauthenticated quota."""
    delay = 5.0
    last: BaseException | None = None
    for i in range(1, attempts + 1):
        try:
            fn()
            return
        except (HfHubHTTPError, LocalEntryNotFoundError, OSError) as exc:
            last = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if isinstance(exc, HfHubHTTPError) and status not in (429, 500, 502, 503, 504) and status is not None:
                raise
            print(
                f"{label}: Hub error {exc!r} (attempt {i}/{attempts}); sleep {delay:.0f}s",
                file=sys.stderr,
            )
            time.sleep(delay)
            delay = min(delay * 2, 120.0)
    assert last is not None
    raise last


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
    _with_hub_retries(
        lambda: snapshot_download(
            repo_id=repo_id,
            revision=revision,
            allow_patterns=allow,
            local_dir=out_dir,
        ),
        label="snapshot_download",
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
            _with_hub_retries(
                lambda: hf_hub_download(
                    repo_id=repo_id,
                    revision=revision,
                    filename="model.safetensors",
                    local_dir=out_dir,
                ),
                label="hf_hub_download",
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
