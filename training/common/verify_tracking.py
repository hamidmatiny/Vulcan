#!/usr/bin/env python3
"""Assert experiment tracking backends recorded a run (ADR-013).

Usage:
  # After MLflow-backed training:
  python training/common/verify_tracking.py --backend mlflow --run-name fsdp-ddp-cpu

  # After W&B offline training:
  python training/common/verify_tracking.py --backend wandb --wandb-dir ./wandb-runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _verify_mlflow(tracking_uri: str, run_name: str, min_metrics: int) -> int:
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri)
    experiments = client.search_experiments()
    runs = []
    for exp in experiments:
        runs.extend(client.search_runs(experiment_ids=[exp.experiment_id], max_results=50))
    named = [r for r in runs if (r.info.run_name or "") == run_name or run_name in (r.info.run_name or "")]
    if not named:
        # Fall back: any run with loss metric.
        named = [r for r in runs if "loss" in (r.data.metrics or {})]
    if not named:
        print(f"FAIL: no MLflow runs found at {tracking_uri} (wanted run_name={run_name!r})", file=sys.stderr)
        return 1
    run = named[0]
    metrics = run.data.metrics or {}
    if "loss" not in metrics and not any(k.startswith("loss") for k in metrics):
        print(f"FAIL: run {run.info.run_id} missing loss metric; got {sorted(metrics)}", file=sys.stderr)
        return 1
    if len(metrics) < min_metrics:
        print(f"FAIL: expected ≥{min_metrics} metrics, got {len(metrics)}: {sorted(metrics)}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "backend": "mlflow",
                "run_id": run.info.run_id,
                "run_name": run.info.run_name,
                "metrics": metrics,
            },
            indent=2,
        )
    )
    return 0


def _verify_wandb(wandb_dir: Path, min_files: int) -> int:
    if not wandb_dir.is_dir():
        print(f"FAIL: wandb dir missing: {wandb_dir}", file=sys.stderr)
        return 1
    # Offline runs land as wandb/offline-run-* or under WANDB_DIR/wandb/offline-run-*.
    candidates = list(wandb_dir.rglob("offline-run-*"))
    candidates = [p for p in candidates if p.is_dir()]
    if not candidates:
        print(f"FAIL: no offline-run-* under {wandb_dir}", file=sys.stderr)
        return 1
    run_dir = max(candidates, key=lambda p: p.stat().st_mtime)
    files = [p for p in run_dir.rglob("*") if p.is_file()]
    if len(files) < min_files:
        print(f"FAIL: offline run {run_dir} has {len(files)} files (<{min_files})", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "backend": "wandb",
                "run_dir": str(run_dir),
                "file_count": len(files),
                "sample_files": [p.name for p in sorted(files)[:8]],
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["mlflow", "wandb"], required=True)
    parser.add_argument("--tracking-uri", default="http://127.0.0.1:9014")
    parser.add_argument("--run-name", default="fsdp-ddp-cpu")
    parser.add_argument("--wandb-dir", type=Path, default=Path("wandb-runs"))
    parser.add_argument("--min-metrics", type=int, default=1)
    parser.add_argument("--min-files", type=int, default=1)
    args = parser.parse_args()
    if args.backend == "mlflow":
        return _verify_mlflow(args.tracking_uri, args.run_name, args.min_metrics)
    return _verify_wandb(args.wandb_dir, args.min_files)


if __name__ == "__main__":
    raise SystemExit(main())
