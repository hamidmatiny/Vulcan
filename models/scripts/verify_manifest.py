#!/usr/bin/env python3
"""Verify on-disk artifacts match models/MANIFEST.md / sha256sums.txt."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import ARTIFACTS_ROOT, MANIFEST_PATH, load_pins, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated model ids to verify (default: all pins).",
    )
    args = parser.parse_args()
    wanted = {m.strip() for m in args.models.split(",") if m.strip()}

    pins = load_pins()
    if not MANIFEST_PATH.is_file():
        print(f"FAIL: {MANIFEST_PATH} missing", file=sys.stderr)
        return 1

    text = MANIFEST_PATH.read_text(encoding="utf-8")
    fail = 0

    for model_id, spec in pins["models"].items():
        if wanted and model_id not in wanted:
            continue
        export = spec["export"]
        rel_dir = export["relative_dir"]
        artifact_dir = Path(__file__).resolve().parents[1] / rel_dir
        primary = artifact_dir / export["primary_file"]
        if not primary.is_file():
            print(f"FAIL: {model_id}: missing {primary}")
            fail = 1
            continue

        actual = sha256_file(primary)
        # Prefer sha256sums.txt; also require MANIFEST to mention the digest.
        sums_path = artifact_dir / "sha256sums.txt"
        if sums_path.is_file():
            expected_line = None
            for line in sums_path.read_text(encoding="utf-8").splitlines():
                if line.endswith(f"  {primary.name}"):
                    expected_line = line.split()[0]
                    break
            if expected_line and expected_line != actual:
                print(f"FAIL: {model_id}: sha256sums mismatch for {primary.name}")
                fail = 1
                continue

        if actual not in text:
            print(f"FAIL: {model_id}: digest {actual} not recorded in MANIFEST.md")
            fail = 1
            continue

        # Soft check: revision pin appears for HF models
        rev = spec["source"].get("revision")
        if rev and rev not in text:
            print(f"FAIL: {model_id}: revision {rev} not in MANIFEST.md")
            fail = 1
            continue

        print(f"OK: {model_id} {primary.name} sha256={actual}")

    if wanted:
        known = set(pins["models"])
        unknown = sorted(wanted - known)
        if unknown:
            print(f"FAIL: unknown model id(s): {', '.join(unknown)}")
            fail = 1

    # Ensure artifact root exists for docs
    _ = ARTIFACTS_ROOT
    # Ban accidental unpinned "latest" wording in pins
    raw_pins = Path(__file__).resolve().parents[1] / "pins.json"
    if re.search(r'"revision"\s*:\s*"main"', raw_pins.read_text(encoding="utf-8")):
        print("FAIL: pins.json must not use revision=main")
        fail = 1

    return fail


if __name__ == "__main__":
    raise SystemExit(main())
