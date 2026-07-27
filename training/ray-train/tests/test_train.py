"""Ray Train CPU job completes with schema-valid result."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_ray_train_completes(tmp_path: Path) -> None:
    out = tmp_path / "out"
    spec = {
        "schema_version": 1,
        "backend": "ray-train",
        "model_id": "reference-tiny-llm",
        "dataset": {"kind": "synthetic_tokens", "num_samples": 32, "seq_len": 8},
        "hyperparameters": {
            "max_steps": 4,
            "batch_size": 2,
            "learning_rate": 1e-3,
            "checkpoint_every_steps": 2,
            "seed": 0,
        },
        "distributed": {"world_size": 2, "dist_backend": "gloo", "strategy": "ray_train"},
        "cpu_dev_mode": True,
        "output_dir": str(out),
        "resume": True,
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONHASHSEED": "0", "RAY_DEDUP_LOGS": "0"}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "training" / "ray-train" / "train.py"), "--spec", str(spec_path)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-4000:] + proc.stdout[-2000:]
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "completed"
    assert result["backend"] == "ray-train"
    assert result["metrics"]["steps_completed"] == 4
