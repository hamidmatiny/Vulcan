"""SIGTERM → checkpoint → resume for FSDP/DDP CPU backend."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_ddp_completes(tmp_path: Path) -> None:
    out = tmp_path / "out"
    spec = {
        "schema_version": 1,
        "backend": "fsdp-ddp",
        "model_id": "reference-tiny-llm",
        "dataset": {"kind": "synthetic_tokens", "num_samples": 32, "seq_len": 8},
        "hyperparameters": {
            "max_steps": 4,
            "batch_size": 2,
            "learning_rate": 1e-3,
            "checkpoint_every_steps": 2,
            "seed": 0,
        },
        "distributed": {"world_size": 2, "dist_backend": "gloo", "strategy": "ddp"},
        "cpu_dev_mode": True,
        "output_dir": str(out),
        "resume": True,
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "VULCAN_DDP_MASTER_PORT": "29521",
        "PYTHONHASHSEED": "0",
    }
    proc = subprocess.run(
        [sys.executable, str(ROOT / "training" / "fsdp-ddp" / "train.py"), "--spec", str(spec_path)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "completed"
    assert result["metrics"]["steps_completed"] == 4
    assert (out / "checkpoint.pt").is_file()


def test_sigterm_resume(tmp_path: Path) -> None:
    out = tmp_path / "out"
    spec = {
        "schema_version": 1,
        "backend": "fsdp-ddp",
        "model_id": "reference-tiny-llm",
        "dataset": {"kind": "synthetic_tokens", "num_samples": 64, "seq_len": 8},
        "hyperparameters": {
            "max_steps": 40,
            "batch_size": 2,
            "learning_rate": 1e-3,
            "checkpoint_every_steps": 1,
            "seed": 0,
        },
        "distributed": {"world_size": 2, "dist_backend": "gloo", "strategy": "ddp"},
        "cpu_dev_mode": True,
        "output_dir": str(out),
        "resume": True,
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "VULCAN_DDP_MASTER_PORT": "29522",
        "PYTHONHASHSEED": "0",
        "VULCAN_TRAIN_STEP_SLEEP": "0.05",
    }
    cmd = [sys.executable, str(ROOT / "training" / "fsdp-ddp" / "train.py"), "--spec", str(spec_path)]
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
    deadline = time.time() + 60
    interrupted_step = 0
    while time.time() < deadline:
        ckpt = out / "checkpoint.pt"
        if ckpt.is_file():
            import torch

            payload = torch.load(ckpt, map_location="cpu", weights_only=False)
            interrupted_step = int(payload.get("step", 0))
            if interrupted_step >= 2:
                proc.send_signal(signal.SIGTERM)
                break
        time.sleep(0.05)
    else:
        proc.kill()
        pytest.fail("timed out waiting for checkpoint before SIGTERM")

    proc.wait(timeout=90)
    assert interrupted_step >= 2
    assert interrupted_step < 40

    # Resume to completion (no step sleep)
    env2 = {**env, "VULCAN_TRAIN_STEP_SLEEP": "0"}
    proc2 = subprocess.run(cmd, cwd=str(ROOT), env=env2, capture_output=True, text=True, check=False)
    assert proc2.returncode == 0, proc2.stderr + proc2.stdout
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "completed"
    assert result["metrics"]["steps_completed"] == 40
    assert result.get("resumed_from_checkpoint") is True
