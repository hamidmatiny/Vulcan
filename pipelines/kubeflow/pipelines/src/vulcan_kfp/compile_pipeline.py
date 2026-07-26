"""Compile the Vulcan KFP pipeline to YAML (no cluster required)."""

from __future__ import annotations

import argparse
from pathlib import Path

from kfp import compiler

from vulcan_kfp.pipeline import vulcan_reference_tiny_llm_pipeline


def default_output() -> Path:
    return Path(__file__).resolve().parents[2] / "compiled" / "vulcan-reference-tiny-llm.yaml"


def compile_to(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    compiler.Compiler().compile(
        pipeline_func=vulcan_reference_tiny_llm_pipeline,
        package_path=str(path),
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile Vulcan KFP pipeline to YAML")
    parser.add_argument("-o", "--output", type=Path, default=default_output())
    args = parser.parse_args(argv)
    out = compile_to(args.output)
    print(f"compiled: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
