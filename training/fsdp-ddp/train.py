#!/usr/bin/env python3
"""FSDP/DDP CPU training backend (gloo, world_size=2) — ADR-009 / ADR-010."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
from torch.nn.parallel import DistributedDataParallel as DDP

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "contracts" / "training-job-contract" / "src"))

from training.common.runtime import (  # noqa: E402
    MAX_FINAL_LOSS,
    TinyCausalLM,
    TrainState,
    default_spec,
    load_checkpoint,
    run_local_steps,
    save_checkpoint,
    seed_everything,
    verify_checkpoint_forward,
    write_result,
)
from vulcan_training_contract.validate import (  # noqa: E402
    validate_training_job_result,
    validate_training_job_spec,
)


def _worker(rank: int, world_size: int, spec: dict, checkpoint_path: Path, stop_file: Path) -> None:
    os.environ["MASTER_ADDR"] = "127.0.0.1"
    os.environ["MASTER_PORT"] = os.environ.get("VULCAN_DDP_MASTER_PORT", "29511")
    dist.init_process_group(
        backend=spec["distributed"]["dist_backend"],
        rank=rank,
        world_size=world_size,
    )
    seed_everything(int(spec["hyperparameters"].get("seed", 0)) + rank)
    device = torch.device("cpu")
    model = TinyCausalLM().to(device)
    # cpu_dev: DDP wrap for both ddp and fsdp labels (full FSDP is GPU/manual — ADR-009).
    model = DDP(model)

    hp = spec["hyperparameters"]
    state = TrainState(max_steps=int(hp["max_steps"]))
    raw_model = model.module
    if spec.get("resume", True):
        # All ranks load the same checkpoint file when present.
        load_checkpoint(checkpoint_path, raw_model, state)

    optimizer = torch.optim.AdamW(model.parameters(), lr=float(hp["learning_rate"]))

    class _StopFile:
        stop_requested = False

        def poll(self) -> None:
            if stop_file.is_file():
                self.stop_requested = True

    stopper = _StopFile()

    def _after_step(_state: TrainState) -> None:
        stopper.poll()

    wall = run_local_steps(
        model,
        optimizer,
        state,
        batch_size=int(hp["batch_size"]),
        seq_len=int(spec["dataset"]["seq_len"]),
        vocab_size=raw_model.vocab_size,
        device=device,
        checkpoint_path=checkpoint_path,
        checkpoint_every=int(hp.get("checkpoint_every_steps", 2)),
        stopper=stopper,  # type: ignore[arg-type]
        is_rank0=(rank == 0),
        after_step=_after_step,
    )
    # Sync interrupt across ranks so nobody hangs in the process group.
    flag = torch.tensor([1 if state.interrupted else 0], dtype=torch.long)
    dist.all_reduce(flag, op=dist.ReduceOp.MAX)
    if int(flag.item()) == 1:
        state.interrupted = True
        if rank == 0:
            save_checkpoint(checkpoint_path, raw_model, state)
            write_result(
                Path(spec["output_dir"]),
                backend="fsdp-ddp",
                checkpoint_path=checkpoint_path,
                state=state,
                samples_per_sec=0.0,
                steps_per_sec=0.0,
                wall_clock_seconds=wall,
                cpu_dev_mode=bool(spec["cpu_dev_mode"]),
            )
        dist.destroy_process_group()
        return

    if rank == 0:
        steps = max(state.step, 1)
        samples = steps * int(hp["batch_size"]) * world_size
        result = write_result(
            Path(spec["output_dir"]),
            backend="fsdp-ddp",
            checkpoint_path=checkpoint_path,
            state=state,
            samples_per_sec=samples / wall if wall > 0 else 0.0,
            steps_per_sec=steps / wall if wall > 0 else 0.0,
            wall_clock_seconds=wall,
            cpu_dev_mode=bool(spec["cpu_dev_mode"]),
        )
        validate_training_job_result(result)
        if state.completed and result["metrics"]["final_loss"] > MAX_FINAL_LOSS:
            raise RuntimeError(f"final_loss too high: {result['metrics']['final_loss']}")
        verify_checkpoint_forward(checkpoint_path, vocab_size=raw_model.vocab_size)

    dist.destroy_process_group()


def run(spec: dict) -> int:
    validate_training_job_spec(spec)
    out = Path(spec["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    ckpt = out / "checkpoint.pt"
    stop_file = out / "STOP"
    if stop_file.exists():
        stop_file.unlink()
    world_size = int(spec["distributed"]["world_size"])

    def _parent_sigterm(signum: int, frame) -> None:  # noqa: ANN001, ARG001
        stop_file.write_text("1\n", encoding="utf-8")

    signal_mod = __import__("signal")
    signal_mod.signal(signal_mod.SIGTERM, _parent_sigterm)
    signal_mod.signal(signal_mod.SIGINT, _parent_sigterm)

    mp.spawn(
        _worker,
        args=(world_size, spec, ckpt, stop_file),
        nprocs=world_size,
        join=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=None)
    parser.add_argument("--strategy", choices=["ddp", "fsdp"], default="ddp")
    parser.add_argument("--output-dir", type=Path, default=Path("training/results/fsdp-ddp"))
    args = parser.parse_args()
    if args.spec:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    else:
        spec = default_spec("fsdp-ddp", args.strategy, str(args.output_dir))
    return run(spec)


if __name__ == "__main__":
    raise SystemExit(main())
