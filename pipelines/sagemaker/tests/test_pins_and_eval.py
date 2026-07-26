"""Pin identity + evaluation metrics (no AWS)."""

from __future__ import annotations

from pathlib import Path

from vulcan_sagemaker.evaluate import evaluate_from_train_metrics, run_evaluation
from vulcan_sagemaker.pins import MODEL_ID, load_reference_llm_pin
from vulcan_sagemaker.train import run_training, simulate_finetune


def test_pin_matches_phase1_gpt2() -> None:
    pin = load_reference_llm_pin()
    assert pin.model_id == MODEL_ID
    assert pin.repo_id == "openai-community/gpt2"
    assert pin.revision == "607a30d783dfa663caf39e06633721c8d4cfcd7e"
    assert pin.modality == "llm"


def test_simulate_train_and_eval_deterministic(tmp_path: Path) -> None:
    metrics = run_training(output_dir=tmp_path / "model", total_steps=20)
    assert metrics["mode"] == "simulate"
    assert metrics["model_id"] == MODEL_ID
    assert (tmp_path / "model" / "train_metrics.json").is_file()

    evaluation = run_evaluation(model_dir=tmp_path / "model", output_dir=tmp_path / "eval")
    assert evaluation["eval_loss"] > metrics["train_loss"]
    assert evaluation["perplexity"] > 1.0
    assert evaluation["revision"] == load_reference_llm_pin().revision
    assert (tmp_path / "eval" / "evaluation.json").is_file()
    assert (tmp_path / "eval" / "evaluation_report.json").is_file()


def test_evaluate_from_train_metrics_stable() -> None:
    m = simulate_finetune(total_steps=10)
    a = evaluate_from_train_metrics(m)
    b = evaluate_from_train_metrics(m)
    assert a == b
