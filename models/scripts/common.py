"""Shared helpers for model fetch/export scripts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MODELS_ROOT = Path(__file__).resolve().parents[1]
PINS_PATH = MODELS_ROOT / "pins.json"
ARTIFACTS_ROOT = MODELS_ROOT / "artifacts"
MANIFEST_PATH = MODELS_ROOT / "MANIFEST.md"


def load_pins() -> dict[str, Any]:
    with PINS_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise TypeError("pins.json root must be an object")
    return data


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def write_sidecar_hashes(artifact_dir: Path, files: list[Path]) -> dict[str, str]:
    """Write sha256sums.txt next to artifacts; return {relative_name: hex}."""
    hashes: dict[str, str] = {}
    lines: list[str] = []
    for path in sorted(files, key=lambda p: p.name):
        hexdigest = sha256_file(path)
        hashes[path.name] = hexdigest
        lines.append(f"{hexdigest}  {path.name}")
    (artifact_dir / "sha256sums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return hashes


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
