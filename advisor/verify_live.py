"""Live CI helper: run full advisor graph and exit non-zero if ungrounded."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from advisor.graph import run_advisor  # noqa: E402
from advisor.non_fabrication import EvidenceItem, assert_answer_grounded, extract_numbers  # noqa: E402


QUESTION = "which backend should I use for lowest cost per token right now?"


def main() -> int:
    use_llm = (ROOT / "models/artifacts/llm/gpt2-small/model.safetensors").is_file()
    result = run_advisor(QUESTION, use_local_llm=use_llm)
    evidence = [
        EvidenceItem(
            tool=e["tool"],
            kind=e["kind"],
            key=e["key"],
            value=e["value"],
            value_str=e["value_str"],
        )
        for e in result["evidence"]
    ]
    assert_answer_grounded(result["answer"], evidence)
    if not result.get("prometheus", {}).get("cost_per_token", {}).get("count"):
        print("FAIL: prometheus cost_per_token empty", file=sys.stderr)
        return 1
    if not result.get("benchmarks", {}).get("count"):
        print("FAIL: benchmarks empty", file=sys.stderr)
        return 1
    if not result.get("routing", {}).get("selected_backend"):
        print("FAIL: routing missing selected_backend", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "answer": result["answer"],
                "recommendation": result["recommendation"],
                "evidence_count": len(evidence),
                "numbers_in_answer": extract_numbers(result["answer"]),
                "synthesis_mode": result.get("synthesis_mode"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
