"""Shared CPU training helpers for Vulcan phase-18 backends (ADR-009 / ADR-010)."""

from __future__ import annotations

import json
import os
import random
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import torch
import torch.nn as nn
import torch.nn.functional as F

# Structural loss ceiling for CI (not a quality claim).
MAX_FINAL_LOSS = 50.0


def seed_everything(seed: int = 0) -> None:
    os.environ.setdefault("PYTHONHASHSEED", "0")
    random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)


class TinyCausalLM(nn.Module):
    """CPU-dev stand-in for reference-tiny-llm (GPT-2 small config family).

    Full GPT-2 weights are too heavy for world_size=2 gloo CI; this tiny model
    keeps the same model_id in the job contract while remaining structurally
    verifiable (forward + checkpoint load).
    """

    def __init__(self, vocab_size: int = 512, d_model: int = 64, n_layer: int = 2) -> None:
        super().__init__()
        self.vocab_size = vocab_size
        self.embed = nn.Embedding(vocab_size, d_model)
        layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=4,
            dim_feedforward=128,
            batch_first=True,
            activation="gelu",
        )
        self.blocks = nn.TransformerEncoder(layer, num_layers=n_layer)
        self.lm_head = nn.Linear(d_model, vocab_size, bias=False)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        x = self.embed(input_ids)
        x = self.blocks(x)
        return self.lm_head(x)


def synthetic_batch(
    batch_size: int,
    seq_len: int,
    vocab_size: int,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor]:
    ids = torch.randint(0, vocab_size, (batch_size, seq_len), device=device)
    # Next-token targets: shift left by one; last position predicts random.
    targets = torch.roll(ids, shifts=-1, dims=1)
    return ids, targets


def loss_fn(logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    return F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1))


@dataclass
class TrainState:
    step: int = 0
    max_steps: int = 8
    loss_curve: list[dict[str, float | int]] = field(default_factory=list)
    completed: bool = False
    interrupted: bool = False
    resumed: bool = False


class SignalStopper:
    """SIGTERM/SIGINT → cooperative stop (checkpoint-then-exit pattern)."""

    def __init__(self) -> None:
        self.stop_requested = False

    def install(self) -> None:
        def _handler(signum: int, frame: Any) -> None:  # noqa: ARG001
            self.stop_requested = True

        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)


def _unwrap(model: nn.Module) -> nn.Module:
    return model.module if hasattr(model, "module") else model  # type: ignore[return-value]


def save_checkpoint(path: Path, model: nn.Module, state: TrainState, extra: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model_state": _unwrap(model).state_dict(),
        "step": state.step,
        "loss_curve": state.loss_curve,
        "completed": state.completed,
        "extra": extra or {},
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, tmp)
    tmp.replace(path)


def load_checkpoint(path: Path, model: nn.Module, state: TrainState) -> bool:
    if not path.is_file():
        return False
    payload = torch.load(path, map_location="cpu", weights_only=False)
    _unwrap(model).load_state_dict(payload["model_state"])
    state.step = int(payload.get("step", 0))
    state.loss_curve = list(payload.get("loss_curve") or [])
    state.completed = bool(payload.get("completed", False))
    state.resumed = True
    return True


def verify_checkpoint_forward(path: Path, vocab_size: int = 512) -> None:
    """Structural check: load checkpoint and run one forward (ADR-009)."""
    model = TinyCausalLM(vocab_size=vocab_size)
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model.load_state_dict(payload["model_state"])
    model.eval()
    with torch.no_grad():
        x = torch.randint(0, vocab_size, (1, 8))
        logits = model(x)
    assert logits.shape == (1, 8, vocab_size)


def write_result(
    out_dir: Path,
    *,
    backend: str,
    checkpoint_path: Path,
    state: TrainState,
    samples_per_sec: float,
    steps_per_sec: float,
    wall_clock_seconds: float,
    cpu_dev_mode: bool,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    status = "completed" if state.completed else ("interrupted" if state.interrupted else "failed")
    final_loss = float(state.loss_curve[-1]["loss"]) if state.loss_curve else 0.0
    result = {
        "schema_version": 1,
        "backend": backend,
        "model_id": "reference-tiny-llm",
        "status": status,
        "checkpoint_path": str(checkpoint_path),
        "metrics": {
            "loss_curve": state.loss_curve,
            "samples_per_sec": float(samples_per_sec),
            "steps_per_sec": float(steps_per_sec),
            "wall_clock_seconds": float(wall_clock_seconds),
            "final_loss": final_loss,
            "steps_completed": int(state.step),
        },
        "resumed_from_checkpoint": bool(state.resumed),
        "cpu_dev_mode": bool(cpu_dev_mode),
        "source": "static_reference_assumption",
    }
    (out_dir / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def default_spec(backend: str, strategy: str, output_dir: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "backend": backend,
        "model_id": "reference-tiny-llm",
        "dataset": {"kind": "synthetic_tokens", "num_samples": 64, "seq_len": 16},
        "hyperparameters": {
            "max_steps": 8,
            "batch_size": 2,
            "learning_rate": 1e-3,
            "checkpoint_every_steps": 2,
            "seed": 0,
        },
        "distributed": {
            "world_size": 2,
            "dist_backend": "gloo",
            "strategy": strategy,
        },
        "cpu_dev_mode": True,
        "output_dir": output_dir,
        "resume": True,
    }


def run_local_steps(
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    state: TrainState,
    *,
    batch_size: int,
    seq_len: int,
    vocab_size: int,
    device: torch.device,
    checkpoint_path: Path,
    checkpoint_every: int,
    stopper: SignalStopper | None = None,
    is_rank0: bool = True,
    after_step: Callable[[TrainState], None] | None = None,
) -> float:
    """Run training steps; returns wall-clock seconds."""
    t0 = time.perf_counter()
    model.train()
    while state.step < state.max_steps:
        if stopper and stopper.stop_requested:
            state.interrupted = True
            if is_rank0:
                save_checkpoint(checkpoint_path, model, state)
            break
        ids, targets = synthetic_batch(batch_size, seq_len, vocab_size, device)
        optimizer.zero_grad(set_to_none=True)
        logits = model(ids)
        loss = loss_fn(logits, targets)
        loss.backward()
        optimizer.step()
        state.step += 1
        sleep_s = float(os.environ.get("VULCAN_TRAIN_STEP_SLEEP", "0") or 0)
        if sleep_s > 0:
            time.sleep(sleep_s)
        if is_rank0:
            state.loss_curve.append({"step": state.step, "loss": float(loss.detach().cpu())})
            if state.step % checkpoint_every == 0:
                save_checkpoint(checkpoint_path, model, state)
        if after_step:
            after_step(state)
    else:
        state.completed = True
        if is_rank0:
            save_checkpoint(checkpoint_path, model, state)
    return time.perf_counter() - t0
