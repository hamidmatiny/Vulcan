"""Reference fine-tune loop with checkpoint-on-SIGTERM.

Models the phase-1 ``reference-tiny-llm`` (GPT-2 small) fine-tuning path without
requiring torch/GPU. Phase 12's real training Job should call the same contract:
persist on SIGTERM, resume from the last completed step on restart.
"""

from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


CHECKPOINT_FILENAME = "checkpoint.json"
MODEL_ID = "reference-tiny-llm"
WORKLOAD = "gpt2-finetune"


@dataclass
class JobState:
    """Serializable training state (stand-in for optimizer + weights)."""

    model_id: str = MODEL_ID
    workload: str = WORKLOAD
    step: int = 0
    total_steps: int = 0
    epoch: int = 0
    loss: float = 1.0
    # Deterministic pseudo-weights so resume can prove continuity without GPU.
    weight_digest: int = 0
    completed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobState:
        return cls(
            model_id=str(data.get("model_id", MODEL_ID)),
            workload=str(data.get("workload", WORKLOAD)),
            step=int(data["step"]),
            total_steps=int(data["total_steps"]),
            epoch=int(data.get("epoch", 0)),
            loss=float(data.get("loss", 1.0)),
            weight_digest=int(data.get("weight_digest", 0)),
            completed=bool(data.get("completed", False)),
        )


class CheckpointStore:
    """Atomic JSON checkpoint writer/reader under a directory."""

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.path = self.directory / CHECKPOINT_FILENAME

    def exists(self) -> bool:
        return self.path.is_file()

    def save(self, state: JobState) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        payload = {
            "version": 1,
            "state": state.to_dict(),
            "saved_at_unix": time.time(),
        }
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        return self.path

    def load(self) -> JobState:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return JobState.from_dict(payload["state"])


class FineTuneJob:
    """Long-running GPU job stand-in: steps advance, SIGTERM checkpoints then exits."""

    def __init__(
        self,
        checkpoint_dir: Path | str,
        *,
        total_steps: int = 50,
        step_seconds: float = 0.05,
        on_checkpoint: Callable[[JobState], None] | None = None,
    ) -> None:
        if total_steps < 1:
            raise ValueError("total_steps must be >= 1")
        self.store = CheckpointStore(checkpoint_dir)
        self.step_seconds = step_seconds
        self.on_checkpoint = on_checkpoint
        self._stop_requested = False
        self._checkpointed_on_signal = False

        if self.store.exists():
            self.state = self.store.load()
            # Caller may extend the horizon on resume.
            if total_steps > self.state.total_steps:
                self.state.total_steps = total_steps
        else:
            self.state = JobState(total_steps=total_steps)

    def _handle_sigterm(self, signum: int, frame: Any) -> None:  # noqa: ARG002
        self._stop_requested = True

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        # Local Ctrl-C should behave like preemption for interactive demos.
        signal.signal(signal.SIGINT, self._handle_sigterm)

    def checkpoint(self, *, reason: str = "manual") -> Path:
        path = self.store.save(self.state)
        self._checkpointed_on_signal = reason in {"sigterm", "sigint", "preempt"}
        if self.on_checkpoint is not None:
            self.on_checkpoint(self.state)
        return path

    def _train_one_step(self) -> None:
        # Deterministic update mimicking a tiny SGD step on GPT-2 fine-tune.
        self.state.step += 1
        self.state.epoch = (self.state.step - 1) // max(1, self.state.total_steps // 2)
        self.state.loss = max(0.01, 1.0 / (1.0 + 0.1 * self.state.step))
        self.state.weight_digest = (self.state.weight_digest * 31 + self.state.step) % 1_000_000_007
        if self.step_seconds > 0:
            time.sleep(self.step_seconds)

    def run(self) -> JobState:
        """Run until complete or a stop signal; always leave a checkpoint on signal."""
        while self.state.step < self.state.total_steps:
            if self._stop_requested:
                self.checkpoint(reason="sigterm")
                raise SystemExit(0)
            self._train_one_step()
            # Periodic cheap checkpoints (spot notice may be short; keep recent state).
            if self.state.step % 5 == 0:
                self.checkpoint(reason="periodic")

        self.state.completed = True
        self.checkpoint(reason="complete")
        return self.state


def resume_digest_chain(start_digest: int, from_step: int, to_step: int) -> int:
    """Recompute weight_digest for steps (from_step, to_step] — used by tests."""
    digest = start_digest
    for step in range(from_step + 1, to_step + 1):
        digest = (digest * 31 + step) % 1_000_000_007
    return digest
