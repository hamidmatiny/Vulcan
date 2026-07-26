"""CLI entry for the reference GPT-2 fine-tune checkpoint loop."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vulcan_checkpointing.trainer import FineTuneJob


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reference fine-tune job (phase-1 reference-tiny-llm / GPT-2 path) with "
            "checkpoint-on-SIGTERM. Forward-ref for phase-12 training Job."
        )
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=Path("/tmp/vulcan-checkpoint"),
        help="Directory for checkpoint.json (PVC mount in cluster)",
    )
    parser.add_argument("--total-steps", type=int, default=50)
    parser.add_argument(
        "--step-seconds",
        type=float,
        default=0.05,
        help="Simulated step duration (raise for spot-notice demos)",
    )
    args = parser.parse_args(argv)

    job = FineTuneJob(
        args.checkpoint_dir,
        total_steps=args.total_steps,
        step_seconds=args.step_seconds,
    )
    job.install_signal_handlers()
    start_step = job.state.step
    print(
        f"starting model_id={job.state.model_id} from_step={start_step} "
        f"total_steps={job.state.total_steps} checkpoint_dir={args.checkpoint_dir}",
        flush=True,
    )
    try:
        state = job.run()
    except SystemExit as exc:
        print(
            f"preempted after_step={job.state.step} checkpoint={job.store.path}",
            flush=True,
        )
        return int(exc.code) if isinstance(exc.code, int) else 0

    print(
        f"completed step={state.step} loss={state.loss:.4f} "
        f"weight_digest={state.weight_digest}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
