"""Phase-1 ``reference-tiny-llm`` pin (same source as serving / SageMaker)."""

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


def _pins_path() -> Path:
    return Path(__file__).resolve().parents[5] / "models" / "pins.json"


def load_reference_llm_pin(pins_path: Path | None = None) -> ReferencePin:
    path = pins_path or _pins_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    spec = data["models"][MODEL_ID]
    source = spec["source"]
    return ReferencePin(
        model_id=MODEL_ID,
        modality=spec["modality"],
        repo_id=source["repo_id"],
        revision=source["revision"],
    )
