#!/usr/bin/env python3
"""Render a markdown comparison table from Vulcan benchmark result JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional for quick local use
    Draft202012Validator = None  # type: ignore[misc, assignment]

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "results" / "schema.json"


def load_schema() -> dict[str, Any]:
    with SCHEMA_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise TypeError("results schema root must be an object")
    return data


def load_result(path: Path, schema: dict[str, Any] | None) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise TypeError(f"{path}: root must be an object")
    if schema is not None and Draft202012Validator is not None:
        Draft202012Validator(schema).validate(data)
    return data


def render_table(rows: list[dict[str, Any]]) -> str:
    headers = [
        "backend",
        "modality",
        "model_id",
        "vus",
        "rps",
        "p50_ms",
        "p95_ms",
        "p99_ms",
        "error_rate",
        "requests",
    ]
    lines = [
        "# Vulcan benchmark comparison",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for r in sorted(rows, key=lambda x: (x["backend"], x["modality"])):
        m = r["metrics"]
        lat = m["latency_ms"]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(r["backend"]),
                    str(r["modality"]),
                    str(r["model_id"]),
                    str(r["vus"]),
                    f"{m['throughput_rps']:.3f}",
                    f"{lat['p50']:.3f}",
                    f"{lat['p95']:.3f}",
                    f"{lat['p99']:.3f}",
                    f"{m['error_rate']:.4f}",
                    str(m["requests_total"]),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Result JSON files (default: benchmark/results/*.json)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write markdown to this path (default: stdout)",
    )
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Do not validate against results/schema.json",
    )
    args = parser.parse_args()

    paths = list(args.paths)
    if not paths:
        paths = sorted((ROOT / "results").glob("*.json"))
        paths = [p for p in paths if p.name != "schema.json"]

    if not paths:
        print("no result files found", file=sys.stderr)
        return 1

    schema = None if args.skip_schema else load_schema()
    rows = [load_result(p, schema) for p in paths]
    md = render_table(rows)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
