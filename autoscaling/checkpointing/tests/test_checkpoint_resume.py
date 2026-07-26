"""SIGTERM → checkpoint → resume (no GPU, no real spot interruption)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from vulcan_checkpointing.trainer import (
    CheckpointStore,
    FineTuneJob,
    JobState,
    resume_digest_chain,
)


def test_checkpoint_store_roundtrip(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path)
    state = JobState(step=7, total_steps=20, loss=0.5, weight_digest=42)
    store.save(state)
    loaded = store.load()
    assert loaded.step == 7
    assert loaded.weight_digest == 42
    assert loaded.model_id == "reference-tiny-llm"


def test_resume_continues_digest(tmp_path: Path) -> None:
    job = FineTuneJob(tmp_path, total_steps=10, step_seconds=0)
    job.run()
    assert job.state.completed is True
    assert job.state.step == 10
    expected = resume_digest_chain(0, 0, 10)
    assert job.state.weight_digest == expected

    # Fresh job loads checkpoint and is already complete.
    job2 = FineTuneJob(tmp_path, total_steps=10, step_seconds=0)
    assert job2.state.step == 10
    assert job2.state.completed is True


def test_sigterm_checkpoints_then_resume(tmp_path: Path) -> None:
    """Simulate Karpenter/AWS spot SIGTERM: checkpoint, restart, finish."""
    job = FineTuneJob(tmp_path, total_steps=40, step_seconds=0.02)
    job.install_signal_handlers()

    # Fire SIGTERM after a few steps from another "thread" via os.kill in a timer.
    pid = os.getpid()

    def _arm() -> None:
        # Wait until at least one step lands, then preempt.
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if job.state.step >= 3:
                os.kill(pid, signal.SIGTERM)
                return
            time.sleep(0.01)

    import threading

    threading.Thread(target=_arm, daemon=True).start()

    with pytest.raises(SystemExit) as exc:
        job.run()
    assert exc.value.code == 0
    assert job.store.exists()
    interrupted_step = job.state.step
    assert 3 <= interrupted_step < 40
    assert job.state.completed is False

    resumed = FineTuneJob(tmp_path, total_steps=40, step_seconds=0)
    assert resumed.state.step == interrupted_step
    final = resumed.run()
    assert final.completed is True
    assert final.step == 40
    assert final.weight_digest == resume_digest_chain(0, 0, 40)


def test_subprocess_sigterm_cli(tmp_path: Path) -> None:
    """End-to-end: CLI process gets SIGTERM, second invocation resumes to done."""
    checkpoint_dir = tmp_path / "ckpts"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    cmd = [
        sys.executable,
        "-m",
        "vulcan_checkpointing.cli",
        "--checkpoint-dir",
        str(checkpoint_dir),
        "--total-steps",
        "30",
        "--step-seconds",
        "0.05",
    ]
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # Let a few steps run.
    time.sleep(0.35)
    assert proc.poll() is None, proc.communicate()[0]
    proc.send_signal(signal.SIGTERM)
    out, _ = proc.communicate(timeout=5)
    assert proc.returncode == 0, out
    assert "preempted" in out
    store = CheckpointStore(checkpoint_dir)
    assert store.exists()
    mid = store.load().step
    assert 1 <= mid < 30

    done = subprocess.run(
        cmd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "completed" in done.stdout
    final = store.load()
    assert final.completed is True
    assert final.step == 30
