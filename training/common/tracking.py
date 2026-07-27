"""Pluggable experiment tracking (ADR-013).

Backends: ``none`` (default), ``mlflow`` (self-hosted), ``wandb`` (offline only).
Select with ``VULCAN_TRACKER_BACKEND``. W&B never calls wandb.ai in CI/local defaults
(same spirit as SageMaker/Bedrock moto — no live cloud).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping


class ExperimentTracker(ABC):
    """Minimal tracking surface shared by MLflow and W&B implementations."""

    @abstractmethod
    def start_run(self, name: str, *, tags: Mapping[str, str] | None = None) -> None: ...

    @abstractmethod
    def log_params(self, params: Mapping[str, Any]) -> None: ...

    @abstractmethod
    def log_metrics(self, metrics: Mapping[str, float], *, step: int | None = None) -> None: ...

    @abstractmethod
    def log_artifact(self, path: str | Path) -> None: ...

    @abstractmethod
    def end_run(self) -> None: ...

    def __enter__(self) -> ExperimentTracker:
        return self

    def __exit__(self, *exc: object) -> None:
        self.end_run()


class NullTracker(ExperimentTracker):
    """Default no-op — existing training jobs stay unaffected."""

    def start_run(self, name: str, *, tags: Mapping[str, str] | None = None) -> None:
        return None

    def log_params(self, params: Mapping[str, Any]) -> None:
        return None

    def log_metrics(self, metrics: Mapping[str, float], *, step: int | None = None) -> None:
        return None

    def log_artifact(self, path: str | Path) -> None:
        return None

    def end_run(self) -> None:
        return None


class MlflowTracker(ExperimentTracker):
    """Talks to a self-hosted MLflow tracking server (compose :9014) or file store."""

    def __init__(self, tracking_uri: str | None = None, experiment: str = "vulcan") -> None:
        import mlflow

        self._mlflow = mlflow
        uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI") or "http://127.0.0.1:9014"
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(experiment)
        self._active = False

    def start_run(self, name: str, *, tags: Mapping[str, str] | None = None) -> None:
        self._mlflow.start_run(run_name=name, tags=dict(tags or {}))
        self._active = True

    def log_params(self, params: Mapping[str, Any]) -> None:
        # MLflow params must be strings; coerce.
        self._mlflow.log_params({k: str(v) for k, v in params.items()})

    def log_metrics(self, metrics: Mapping[str, float], *, step: int | None = None) -> None:
        self._mlflow.log_metrics({k: float(v) for k, v in metrics.items()}, step=step)

    def log_artifact(self, path: str | Path) -> None:
        p = Path(path)
        if p.is_file():
            self._mlflow.log_artifact(str(p))

    def end_run(self) -> None:
        if self._active:
            self._mlflow.end_run()
            self._active = False


class WandbTracker(ExperimentTracker):
    """Weights & Biases in offline mode only (ADR-013 — no wandb.ai in CI)."""

    def __init__(self, project: str = "vulcan", dir: str | None = None) -> None:
        mode = os.environ.get("WANDB_MODE", "offline").lower()
        if mode not in {"offline", "disabled"}:
            raise RuntimeError(
                "WandbTracker requires WANDB_MODE=offline|disabled "
                "(ADR-013; same offline spirit as SageMaker/Bedrock moto). "
                f"Got WANDB_MODE={mode!r}"
            )
        os.environ.setdefault("WANDB_MODE", "offline")
        # Never require a real key; offline still wants a placeholder for some SDK versions.
        os.environ.setdefault("WANDB_API_KEY", "")
        os.environ.setdefault("WANDB_ANONYMOUS", "allow")
        import wandb

        self._wandb = wandb
        self._project = project
        self._dir = dir or os.environ.get("WANDB_DIR") or str(Path.cwd() / "wandb-runs")
        Path(self._dir).mkdir(parents=True, exist_ok=True)
        self._run: Any = None

    def start_run(self, name: str, *, tags: Mapping[str, str] | None = None) -> None:
        self._run = self._wandb.init(
            project=self._project,
            name=name,
            dir=self._dir,
            mode="offline",
            tags=list((tags or {}).values()) or None,
            config={},
            reinit=True,
        )

    def log_params(self, params: Mapping[str, Any]) -> None:
        if self._run is not None:
            self._wandb.config.update(dict(params), allow_val_change=True)

    def log_metrics(self, metrics: Mapping[str, float], *, step: int | None = None) -> None:
        if self._run is not None:
            payload = {k: float(v) for k, v in metrics.items()}
            if step is not None:
                self._wandb.log(payload, step=step)
            else:
                self._wandb.log(payload)

    def log_artifact(self, path: str | Path) -> None:
        if self._run is None:
            return
        p = Path(path)
        if p.is_file():
            art = self._wandb.Artifact(p.stem, type="result")
            art.add_file(str(p))
            self._run.log_artifact(art)

    def end_run(self) -> None:
        if self._run is not None:
            self._wandb.finish()
            self._run = None


def get_tracker(
    *,
    backend: str | None = None,
    run_name: str | None = None,
) -> ExperimentTracker:
    """Factory: ``VULCAN_TRACKER_BACKEND`` ∈ {none, mlflow, wandb}."""
    name = (backend or os.environ.get("VULCAN_TRACKER_BACKEND") or "none").strip().lower()
    if name in {"", "none", "off", "null"}:
        return NullTracker()
    if name == "mlflow":
        return MlflowTracker()
    if name in {"wandb", "weights_and_biases", "w&b"}:
        return WandbTracker()
    raise ValueError(f"unknown VULCAN_TRACKER_BACKEND={name!r} (expected none|mlflow|wandb)")


def flatten_params(spec: Mapping[str, Any], *, prefix: str = "") -> dict[str, Any]:
    """Flatten nested training/LoRA specs into tracker-friendly scalar params."""
    out: dict[str, Any] = {}
    for key, value in spec.items():
        path = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, Mapping):
            out.update(flatten_params(value, prefix=path))
        elif isinstance(value, (list, tuple)):
            out[path] = ",".join(str(v) for v in value)
        elif value is None or isinstance(value, (str, int, float, bool)):
            out[path] = value
    return out
