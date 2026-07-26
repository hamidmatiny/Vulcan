"""eval_loss / perplexity — same approach as phase-10 SageMaker evaluate.

Cross-platform comparison point: identical model_id/revision identity and the
same held-out gap formula (corpus-length penalty on train_loss).
"""

from __future__ import annotations

import json
import math
from importlib import resources
from pathlib import Path
from typing import Any

from vulcan_kfp.pins import MODEL_ID, load_reference_llm_pin


def load_eval_corpus() -> str:
    ref = resources.files("vulcan_kfp").joinpath("data/eval_corpus.txt")
    return ref.read_text(encoding="utf-8")


def evaluate_from_train_metrics(
    train_metrics: dict[str, Any],
    corpus: str | None = None,
    *,
    backend: str = "kubeflow",
) -> dict[str, Any]:
    pin = load_reference_llm_pin()
    text = corpus if corpus is not None else load_eval_corpus()
    train_loss = float(train_metrics.get("train_loss", train_metrics.get("loss", 1.0)))
    gap = min(0.5, 0.01 * max(1, len(text.split())))
    eval_loss = train_loss + gap
    perplexity = math.exp(min(eval_loss, 20.0))
    return {
        "model_id": pin.model_id,
        "hub_repo_id": pin.repo_id,
        "revision": pin.revision,
        "modality": pin.modality,
        "eval_loss": round(eval_loss, 6),
        "perplexity": round(perplexity, 6),
        "corpus_tokens_approx": len(text.split()),
        "weight_digest": train_metrics.get("weight_digest"),
        "backend": backend,
        "comparison_note": (
            "Metrics match pipelines/sagemaker evaluate_from_train_metrics "
            "(eval_loss/perplexity on the same pin) for cross-platform comparison."
        ),
    }


def write_evaluation(output_dir: Path, evaluation: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "evaluation.json"
    path.write_text(json.dumps(evaluation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "evaluation_report.json").write_text(
        json.dumps(
            {
                "metrics": [
                    {"Name": "eval_loss", "Value": evaluation["eval_loss"]},
                    {"Name": "perplexity", "Value": evaluation["perplexity"]},
                ],
                "model_id": MODEL_ID,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
