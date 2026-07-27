#!/usr/bin/env python3
"""Ray Train CPU backend (world_size=2 workers) — ADR-009 / ADR-010.

Ray pin MUST match serving/ray-serve: ray[serve]>=2.52.0,<2.53 (CVE floor).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "contracts" / "training-job-contract" / "src"))

os.environ.setdefault("PYTHONHASHSEED", "0")

import torch  # noqa: E402
from ray.train import ScalingConfig  # noqa: E402
from ray.train.torch import TorchTrainer  # noqa: E402

from training.common.runtime import (  # noqa: E402
    MAX_FINAL_LOSS,
    TinyCausalLM,
    TrainState,
    default_spec,
    load_checkpoint,
    run_local_steps,
    seed_everything,
    verify_checkpoint_forward,
    write_result,
)
from vulcan_training_contract.validate import (  # noqa: E402
    validate_training_job_result,
    validate_training_job_spec,
)


def _train_loop(config: dict) -> None:
    import ray.train as ray_train

    spec = config["spec"]
    checkpoint_path = Path(config["checkpoint_path"])
    seed_everything(int(spec["hyperparameters"].get("seed", 0)))
    device = torch.device("cpu")
    model = TinyCausalLM().to(device)
    model = ray_train.torch.prepare_model(model)

    hp = spec["hyperparameters"]
    state = TrainState(max_steps=int(hp["max_steps"]))
    raw = model.module if hasattr(model, "module") else model
    rank = ray_train.get_context().get_world_rank()
    if spec.get("resume", True):
        load_checkpoint(checkpoint_path, raw, state)

    optimizer = torch.optim.AdamW(model.parameters(), lr=float(hp["learning_rate"]))
    wall = run_local_steps(
        model,
        optimizer,
        state,
        batch_size=int(hp["batch_size"]),
        seq_len=int(spec["dataset"]["seq_len"]),
        vocab_size=raw.vocab_size,
        device=device,
        checkpoint_path=checkpoint_path,
        checkpoint_every=int(hp.get("checkpoint_every_steps", 2)),
        is_rank0=(rank == 0),
    )
    if rank == 0:
        steps = max(state.step, 1)
        world = ray_train.get_context().get_world_size()
        samples = steps * int(hp["batch_size"]) * world
        state.completed = state.step >= state.max_steps
        result = write_result(
            Path(spec["output_dir"]),
            backend="ray-train",
            checkpoint_path=checkpoint_path,
            state=state,
            samples_per_sec=samples / wall if wall > 0 else 0.0,
            steps_per_sec=steps / wall if wall > 0 else 0.0,
            wall_clock_seconds=wall,
            cpu_dev_mode=bool(spec["cpu_dev_mode"]),
        )
        validate_training_job_result(result)
        if result["metrics"]["final_loss"] > MAX_FINAL_LOSS:
            raise RuntimeError(f"final_loss too high: {result['metrics']['final_loss']}")
        verify_checkpoint_forward(checkpoint_path, vocab_size=raw.vocab_size)


def run(spec: dict) -> int:
    validate_training_job_spec(spec)
    out = Path(spec["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    ckpt = out / "checkpoint.pt"
    world_size = int(spec["distributed"]["world_size"])

    trainer = TorchTrainer(
        train_loop_per_worker=_train_loop,
        train_loop_config={"spec": spec, "checkpoint_path": str(ckpt)},
        scaling_config=ScalingConfig(num_workers=world_size, use_gpu=False),
    )
    trainer.fit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("training/results/ray-train"))
    args = parser.parse_args()
    if args.spec:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    else:
        spec = default_spec("ray-train", "ray_train", str(args.output_dir))
    return run(spec)


if __name__ == "__main__":
    raise SystemExit(main())
