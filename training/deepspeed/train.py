#!/usr/bin/env python3
"""DeepSpeed CPU ZeRO-1/2 training backend — ADR-009 / ADR-010.

Real GPU ZeRO offload numbers: docs/runbooks/deepspeed-gpu-mode.md (manual only).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "contracts" / "training-job-contract" / "src"))

os.environ.setdefault("PYTHONHASHSEED", "0")
# ADR-009: CI/local cpu_dev must never pick MPS/CUDA — DeepSpeed auto-detects MPS on macOS.
os.environ["DS_ACCELERATOR"] = "cpu"
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import torch  # noqa: E402
import torch.distributed as dist  # noqa: E402
import torch.multiprocessing as mp  # noqa: E402

from training.common.runtime import (  # noqa: E402
    MAX_FINAL_LOSS,
    TinyCausalLM,
    TrainState,
    default_spec,
    load_checkpoint,
    loss_fn,
    save_checkpoint,
    seed_everything,
    synthetic_batch,
    verify_checkpoint_forward,
    write_result,
)
from vulcan_training_contract.validate import (  # noqa: E402
    validate_training_job_result,
    validate_training_job_spec,
)


def zero_config(stage: int, lr: float, batch_size: int) -> dict:
    return {
        "train_batch_size": batch_size * 2,
        "train_micro_batch_size_per_gpu": batch_size,
        "gradient_accumulation_steps": 1,
        "optimizer": {
            "type": "AdamW",
            "params": {
                "lr": lr,
                "betas": [0.9, 0.999],
                "eps": 1e-8,
                "weight_decay": 0.0,
                "torch_adam": True,
            },
        },
        "zero_optimization": {
            "stage": stage,
            "overlap_comm": False,
            "contiguous_gradients": True,
        },
        "fp16": {"enabled": False},
        "wall_clock_breakdown": False,
    }


def _worker(rank: int, world_size: int, spec: dict, checkpoint_path: Path, ds_config: dict) -> None:
    os.environ["DS_ACCELERATOR"] = "cpu"
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    os.environ["MASTER_ADDR"] = "127.0.0.1"
    os.environ["MASTER_PORT"] = os.environ.get("VULCAN_DS_MASTER_PORT", "29531")
    os.environ["LOCAL_RANK"] = str(rank)
    os.environ["RANK"] = str(rank)
    os.environ["WORLD_SIZE"] = str(world_size)

    # Ensure venv scripts (ninja) are on PATH for any optional JIT ops.
    venv_bin = str(Path(sys.executable).resolve().parent)
    os.environ["PATH"] = venv_bin + os.pathsep + os.environ.get("PATH", "")

    import deepspeed
    import deepspeed.ops as ds_ops

    # Optional CPU SHM JIT is not required for gloo cpu_dev and races under mp.spawn.
    ds_ops.__compatible_ops__["deepspeed_shm_comm"] = False

    dist.init_process_group(backend="gloo", rank=rank, world_size=world_size)
    deepspeed.init_distributed(dist_backend="gloo", dist_init_required=False)
    seed_everything(int(spec["hyperparameters"].get("seed", 0)) + rank)
    model = TinyCausalLM()
    hp = spec["hyperparameters"]
    state = TrainState(max_steps=int(hp["max_steps"]))
    if spec.get("resume", True):
        load_checkpoint(checkpoint_path, model, state)

    engine, _, _, _ = deepspeed.initialize(model=model, config_params=ds_config)
    device = torch.device("cpu")
    t0 = time.perf_counter()
    engine.train()
    while state.step < state.max_steps:
        ids, targets = synthetic_batch(
            int(hp["batch_size"]),
            int(spec["dataset"]["seq_len"]),
            model.vocab_size,
            device,
        )
        logits = engine(ids)
        loss = loss_fn(logits, targets)
        engine.backward(loss)
        engine.step()
        state.step += 1
        if rank == 0:
            state.loss_curve.append({"step": state.step, "loss": float(loss.detach().cpu())})
            if state.step % int(hp.get("checkpoint_every_steps", 2)) == 0:
                save_checkpoint(checkpoint_path, engine.module, state)
    state.completed = True
    wall = time.perf_counter() - t0

    if rank == 0:
        save_checkpoint(checkpoint_path, engine.module, state)
        steps = max(state.step, 1)
        samples = steps * int(hp["batch_size"]) * world_size
        result = write_result(
            Path(spec["output_dir"]),
            backend="deepspeed",
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
        verify_checkpoint_forward(checkpoint_path, vocab_size=model.vocab_size)

    if dist.is_initialized():
        dist.destroy_process_group()


def run(spec: dict) -> int:
    validate_training_job_spec(spec)
    out = Path(spec["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    strategy = spec["distributed"]["strategy"]
    stage = 2 if strategy == "deepspeed_zero2" else 1
    hp = spec["hyperparameters"]
    ds_config = zero_config(stage, float(hp["learning_rate"]), int(hp["batch_size"]))
    (out / "ds_config.json").write_text(json.dumps(ds_config, indent=2) + "\n", encoding="utf-8")
    ckpt = out / "checkpoint.pt"
    world_size = int(spec["distributed"]["world_size"])
    mp.spawn(_worker, args=(world_size, spec, ckpt, ds_config), nprocs=world_size, join=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=None)
    parser.add_argument("--zero-stage", type=int, choices=[1, 2], default=1)
    parser.add_argument("--output-dir", type=Path, default=Path("training/results/deepspeed"))
    args = parser.parse_args()
    if args.spec:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    else:
        strat = "deepspeed_zero2" if args.zero_stage == 2 else "deepspeed_zero1"
        spec = default_spec("deepspeed", strat, str(args.output_dir))
    return run(spec)


if __name__ == "__main__":
    raise SystemExit(main())
