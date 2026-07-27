"""Unit tests for pluggable experiment tracking (ADR-013)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from training.common.tracking import (  # noqa: E402
    NullTracker,
    WandbTracker,
    flatten_params,
    get_tracker,
)


def test_default_backend_is_null() -> None:
    os.environ.pop("VULCAN_TRACKER_BACKEND", None)
    t = get_tracker()
    assert isinstance(t, NullTracker)
    t.start_run("x")
    t.log_params({"a": 1})
    t.log_metrics({"loss": 1.0}, step=1)
    t.log_artifact(__file__)
    t.end_run()


def test_flatten_params() -> None:
    flat = flatten_params({"hyperparameters": {"lr": 0.1, "seed": 0}, "backend": "fsdp-ddp"})
    assert flat["backend"] == "fsdp-ddp"
    assert flat["hyperparameters.lr"] == 0.1


def test_wandb_rejects_online_mode(tmp_path: Path) -> None:
    os.environ["WANDB_MODE"] = "online"
    with pytest.raises(RuntimeError, match="offline"):
        WandbTracker(dir=str(tmp_path))
    os.environ["WANDB_MODE"] = "offline"


def test_mlflow_file_store_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("mlflow")
    uri = f"file:{tmp_path / 'mlruns'}"
    os.environ["VULCAN_TRACKER_BACKEND"] = "mlflow"
    os.environ["MLFLOW_TRACKING_URI"] = uri
    from training.common.tracking import MlflowTracker

    tracker = MlflowTracker(tracking_uri=uri, experiment="vulcan-test")
    tracker.start_run("unit-mlflow")
    tracker.log_params({"backend": "fsdp-ddp"})
    tracker.log_metrics({"loss": 1.23}, step=1)
    tracker.end_run()

    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=uri)
    runs = []
    for exp in client.search_experiments():
        runs.extend(client.search_runs([exp.experiment_id]))
    assert runs
    assert abs(float(runs[0].data.metrics["loss"]) - 1.23) < 1e-6


def test_wandb_offline_creates_run_dir(tmp_path: Path) -> None:
    pytest.importorskip("wandb")
    os.environ["WANDB_MODE"] = "offline"
    os.environ["WANDB_DIR"] = str(tmp_path)
    tracker = WandbTracker(dir=str(tmp_path), project="vulcan-test")
    tracker.start_run("unit-wandb")
    tracker.log_params({"backend": "fsdp-ddp"})
    tracker.log_metrics({"loss": 0.5}, step=1)
    tracker.end_run()
    offline = list(tmp_path.rglob("offline-run-*"))
    assert offline, f"expected offline-run under {tmp_path}"
