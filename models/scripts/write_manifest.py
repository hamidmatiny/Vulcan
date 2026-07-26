#!/usr/bin/env python3
"""Regenerate models/MANIFEST.md from pins.json + artifact sha256sums."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from common import ARTIFACTS_ROOT, MANIFEST_PATH, load_pins, sha256_file


def _read_sha256sums(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition("  ")
        if name:
            out[name] = digest
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-artifacts",
        action="store_true",
        help="Fail if primary artifacts are missing (use after export).",
    )
    args = parser.parse_args()

    pins = load_pins()
    lines: list[str] = [
        "# Model manifest (byte-identical pins)",
        "",
        "Every Vulcan serving backend MUST serve weights whose **sha256** matches this file.",
        "Cross-backend benchmarks are only legitimate when all backends load these pins.",
        "",
        f"**Generated:** {date.today().isoformat()}  ",
        f"**Pins source:** [`pins.json`](./pins.json)",
        "",
        "## Policy",
        "",
        "- CI never downloads GPU builds or runs on GPU hardware (ADR-002).",
        "- Weights live under `models/artifacts/` (gitignored binaries); this manifest is committed.",
        "- Re-export with `python models/scripts/export_*.py` then `python models/scripts/write_manifest.py --require-artifacts`.",
        "",
        "## Models",
        "",
    ]

    missing = False
    for model_id, spec in pins["models"].items():
        export = spec["export"]
        rel_dir = export["relative_dir"]
        primary = export["primary_file"]
        artifact_dir = ARTIFACTS_ROOT.parent / rel_dir
        # relative_dir is like artifacts/llm/gpt2-small under models/
        if not str(rel_dir).startswith("artifacts/"):
            artifact_dir = ARTIFACTS_ROOT / rel_dir
        else:
            artifact_dir = ARTIFACTS_ROOT.parent / rel_dir

        sums = _read_sha256sums(artifact_dir / "sha256sums.txt")
        primary_path = artifact_dir / primary
        primary_sha = sums.get(primary) or (sha256_file(primary_path) if primary_path.is_file() else "MISSING")
        if primary_sha == "MISSING":
            missing = True

        lines.append(f"### `{model_id}`")
        lines.append("")
        lines.append(f"- **Modality:** `{spec['modality']}`")
        source = spec["source"]
        if source.get("hub") == "huggingface":
            lines.append(
                f"- **Source:** Hugging Face `{source['repo_id']}` @ `{source['revision']}`"
            )
            lines.append(f"- **Params (approx):** {source.get('approx_params', 'n/a')}")
        else:
            lines.append(f"- **Source:** {source.get('hub')} `{source.get('name')}` / `{source.get('weights')}`")
            if source.get("weights_url"):
                lines.append(f"- **Upstream URL:** `{source['weights_url']}`")
        lines.append(f"- **Export format:** `{export['format']}`")
        lines.append(f"- **Artifact dir:** `{rel_dir}/`")
        lines.append(f"- **Primary file:** `{primary}`")
        lines.append(f"- **Primary sha256:** `{primary_sha}`")
        lines.append("")
        if sums:
            lines.append("| File | sha256 |")
            lines.append("|------|--------|")
            for name, digest in sorted(sums.items()):
                lines.append(f"| `{name}` | `{digest}` |")
            lines.append("")
        else:
            lines.append("_No `sha256sums.txt` yet — run the export scripts._")
            lines.append("")
        if spec.get("notes"):
            lines.append(f"> {spec['notes']}")
            lines.append("")

    lines.extend(
        [
            "## Verification",
            "",
            "```bash",
            "python models/scripts/verify_manifest.py",
            "```",
            "",
        ]
    )

    MANIFEST_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH}")
    if args.require_artifacts and missing:
        raise SystemExit("primary artifacts missing — run export_llm.py / export_vision.py first")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
