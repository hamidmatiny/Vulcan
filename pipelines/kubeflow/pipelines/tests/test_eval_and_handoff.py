from __future__ import annotations

from pathlib import Path

from vulcan_kfp.evaluate import evaluate_from_train_metrics, write_evaluation
from vulcan_kfp.handoff import build_inferenceservice_yaml, register_and_handoff
from vulcan_kfp.pins import MODEL_ID, load_reference_llm_pin
from vulcan_kfp.train import run_training


def test_pin_matches_phase1() -> None:
    pin = load_reference_llm_pin()
    assert pin.model_id == MODEL_ID
    assert pin.repo_id == "openai-community/gpt2"
    assert pin.revision.startswith("607a30d7")


def test_eval_aligns_with_sagemaker_formula(tmp_path: Path) -> None:
    metrics = run_training(output_dir=tmp_path / "model", total_steps=20)
    evaluation = evaluate_from_train_metrics(metrics)
    write_evaluation(tmp_path / "eval", evaluation)
    assert evaluation["eval_loss"] > metrics["train_loss"]
    assert evaluation["perplexity"] > 1.0
    assert evaluation["backend"] == "kubeflow"
    assert "sagemaker" in evaluation["comparison_note"].lower()


def test_handoff_emits_phase6_shaped_isvc(tmp_path: Path) -> None:
    run_training(output_dir=tmp_path / "model", total_steps=10)
    evaluation = evaluate_from_train_metrics(
        {"train_loss": 0.5, "weight_digest": 1},
    )
    write_evaluation(tmp_path / "eval", evaluation)
    registry = register_and_handoff(
        model_dir=tmp_path / "model",
        eval_dir=tmp_path / "eval",
        output_dir=tmp_path / "handoff",
    )
    assert registry["composed_from"]["kueue_queue"] == "lq-training"
    assert registry["composed_from"]["karpenter_nodepool"] == "vulcan-gpu-mig-large"
    assert registry["composed_from"]["checkpointing"] == "autoscaling/checkpointing"
    isvc = (tmp_path / "handoff" / "inferenceservice.yaml").read_text()
    assert "kind: InferenceService" in isvc
    assert "vulcan.dev/backend: vllm" in isvc
    assert "RawDeployment" in isvc
    assert "9004" in isvc


def test_build_inferenceservice_yaml_contains_metrics() -> None:
    yaml_text = build_inferenceservice_yaml(
        evaluation={"eval_loss": 1.23, "perplexity": 3.42},
    )
    assert 'vulcan.dev/eval_loss: "1.23"' in yaml_text
    assert "vulcan-vllm:cpu" in yaml_text
