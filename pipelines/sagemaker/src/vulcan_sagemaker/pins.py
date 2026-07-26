"""Load the phase-1 ``reference-tiny-llm`` pin (same source of truth as serving)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


MODEL_ID = "reference-tiny-llm"


@dataclass(frozen=True)
class ReferencePin:
    model_id: str
    modality: str
    repo_id: str
    revision: str
    approx_params: str
    artifact_rel_dir: str
    primary_file: str


def _default_pins_path() -> Path:
    # pipelines/sagemaker/src/vulcan_sagemaker/pins.py → repo root
    return Path(__file__).resolve().parents[4] / "models" / "pins.json"


def load_reference_llm_pin(pins_path: Path | None = None) -> ReferencePin:
    path = pins_path or _default_pins_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    spec = data["models"][MODEL_ID]
    source = spec["source"]
    export = spec["export"]
    return ReferencePin(
        model_id=MODEL_ID,
        modality=spec["modality"],
        repo_id=source["repo_id"],
        revision=source["revision"],
        approx_params=str(source.get("approx_params", "")),
        artifact_rel_dir=export["relative_dir"],
        primary_file=export["primary_file"],
    )
