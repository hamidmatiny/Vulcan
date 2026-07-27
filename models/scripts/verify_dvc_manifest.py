#!/usr/bin/env python3
"""Cross-validate DVC-tracked primary outs against sha256sums.txt (ADR-012).

DVC keeps its own content-addressed cache hashes in dvc.lock; this check proves
the *bytes* of each tracked out match the human-readable sha256sums / MANIFEST
source of truth — the two systems must not silently drift.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from common import MODELS_ROOT, sha256_file

ROOT = MODELS_ROOT.parent
DVC_LOCK = ROOT / "dvc.lock"
DVC_YAML = ROOT / "dvc.yaml"

# Stage → (artifact dir relative to models/, primary file name)
STAGE_PRIMARIES = {
    "export-llm": ("artifacts/llm/gpt2-small", "model.safetensors"),
    "export-vision": ("artifacts/vision/resnet18", "model.onnx"),
}


def _load_lock_outs() -> dict[str, list[str]]:
    if not DVC_LOCK.is_file():
        raise FileNotFoundError(f"missing {DVC_LOCK} — run `dvc repro` and commit the lock")
    doc = yaml.safe_load(DVC_LOCK.read_text(encoding="utf-8"))
    stages = doc.get("stages") or {}
    result: dict[str, list[str]] = {}
    for name, body in stages.items():
        outs = body.get("outs") or []
        paths: list[str] = []
        for item in outs:
            if isinstance(item, dict):
                path = item.get("path")
                if path:
                    paths.append(str(path))
            elif isinstance(item, str):
                paths.append(item)
        result[name] = paths
    return result


def _expected_sha256(artifact_dir: Path, primary_name: str) -> str:
    sums = artifact_dir / "sha256sums.txt"
    if not sums.is_file():
        raise FileNotFoundError(f"missing {sums}")
    for line in sums.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1] == primary_name:
            return parts[0]
    raise KeyError(f"{primary_name} not listed in {sums}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    if not DVC_YAML.is_file():
        print(f"FAIL: {DVC_YAML} missing", file=sys.stderr)
        return 1

    fail = 0
    lock_outs = _load_lock_outs()

    for stage, (rel_dir, primary_name) in STAGE_PRIMARIES.items():
        if stage not in lock_outs:
            print(f"FAIL: stage {stage!r} missing from dvc.lock")
            fail = 1
            continue
        expected_rel = f"models/{rel_dir}/{primary_name}"
        if expected_rel not in lock_outs[stage] and primary_name not in " ".join(lock_outs[stage]):
            # Accept either repo-relative path as recorded by DVC.
            matched = any(p.endswith(f"{rel_dir}/{primary_name}") for p in lock_outs[stage])
            if not matched:
                print(f"FAIL: {stage}: expected out ending with {rel_dir}/{primary_name}, got {lock_outs[stage]}")
                fail = 1
                continue

        artifact_dir = MODELS_ROOT / rel_dir
        primary = artifact_dir / primary_name
        if not primary.is_file():
            print(f"FAIL: {stage}: missing on-disk {primary}")
            fail = 1
            continue

        actual = sha256_file(primary)
        try:
            expected = _expected_sha256(artifact_dir, primary_name)
        except (FileNotFoundError, KeyError) as exc:
            print(f"FAIL: {stage}: {exc}")
            fail = 1
            continue

        if actual != expected:
            print(f"FAIL: {stage}: sha256 {actual} != sha256sums {expected}")
            fail = 1
            continue

        print(f"OK: {stage} {primary_name} sha256={actual} (matches sha256sums.txt)")

    # Hard scope guard: lock must not mention training/adapter paths.
    lock_text = DVC_LOCK.read_text(encoding="utf-8")
    for banned in ("training/results", "lora-demo", "adapter_model"):
        if banned in lock_text:
            print(f"FAIL: dvc.lock must not track {banned!r} (ADR-009/011/012)")
            fail = 1

    return fail


if __name__ == "__main__":
    raise SystemExit(main())
