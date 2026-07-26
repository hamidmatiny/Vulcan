"""Load static cost/latency reference figures for the future routing gateway."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def pricing_path() -> Path:
    return Path(__file__).resolve().parents[2] / "pricing-reference.json"


def load_pricing_reference(path: Path | None = None) -> dict[str, Any]:
    data = json.loads((path or pricing_path()).read_text(encoding="utf-8"))
    if data.get("source") != "static_reference":
        raise ValueError("pricing-reference.json must set source=static_reference")
    if "disclaimer" not in data or "models" not in data:
        raise ValueError("pricing-reference.json missing disclaimer or models")
    return data


def cost_for_model(model_id: str, path: Path | None = None) -> dict[str, Any] | None:
    ref = load_pricing_reference(path)
    model = ref.get("models", {}).get(model_id)
    if model is None:
        return None
    return {
        "model_id": model_id,
        "source": ref["source"],
        "as_of": ref.get("as_of"),
        **model,
    }
