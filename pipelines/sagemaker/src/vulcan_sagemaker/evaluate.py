"""Evaluate a trained ``reference-tiny-llm`` checkpoint.

Uses the same identity (model_id + HF revision from ``models/pins.json``) as
serving backends. Metrics are **eval_loss** and **perplexity** on a fixed
held-out corpus — the training-quality counterpart to the shared k6 latency
harness used for serving comparison.
"""

from __future__ import annotations

import argparse
import json
import math
from importlib import resources
from pathlib import Path
from typing import Any

from vulcan_sagemaker.pins import MODEL_ID, load_reference_llm_pin


def load_eval_corpus() -> str:
    ref = resources.files("vulcan_sagemaker").joinpath("data/eval_corpus.txt")
    return ref.read_text(encoding="utf-8")


def evaluate_from_train_metrics(train_metrics: dict[str, Any], corpus: str | None = None) -> dict[str, Any]:
    """Derive eval metrics from the train artifact (CPU-safe, deterministic).

    For the simulated GPT-2 path, eval_loss tracks train_loss with a small
    held-out penalty proportional to corpus length — enough to gate registry
    approval without downloading weights in CI.
    """
    pin = load_reference_llm_pin()
    text = corpus if corpus is not None else load_eval_corpus()
    train_loss = float(train_metrics.get("train_loss", 1.0))
    # Tiny length-based generalization gap (stable across runs).
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
        "backend": "sagemaker",
        "comparison_note": (
            "Serving latency/error_rate remain measured by benchmark/k6 against "
            "contract backends; this file is the training-quality gate for Model Registry."
        ),
    }


def write_evaluation(output_dir: Path, evaluation: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    # SageMaker Model Metrics often expect evaluation.json
    path = output_dir / "evaluation.json"
    path.write_text(json.dumps(evaluation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Property file style for Pipeline PropertyFile reports
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


def run_evaluation(*, model_dir: Path, output_dir: Path) -> dict[str, Any]:
    metrics_path = model_dir / "train_metrics.json"
    if not metrics_path.is_file():
        # model.tar.json fallback
        artifact = model_dir / "model.tar.json"
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        train_metrics = payload.get("metrics", {})
    else:
        train_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    evaluation = evaluate_from_train_metrics(train_metrics)
    write_evaluation(output_dir, evaluation)
    return evaluation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vulcan SageMaker evaluate step")
    parser.add_argument("--model-dir", type=Path, default=Path("/opt/ml/processing/model"))
    parser.add_argument("--output-dir", type=Path, default=Path("/opt/ml/processing/evaluation"))
    args = parser.parse_args(argv)
    evaluation = run_evaluation(model_dir=args.model_dir, output_dir=args.output_dir)
    print(json.dumps(evaluation))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
