"""CLI: run the tool-grounded LangGraph advisor (ADR-014)."""

from __future__ import annotations

import argparse
import json
import sys

from advisor.graph import run_advisor


DEFAULT_QUESTION = "which backend should I use for lowest cost per token right now?"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument(
        "--no-local-llm",
        action="store_true",
        help="Template-only synthesis (skip GPT-2-small commentary)",
    )
    args = parser.parse_args(argv)
    result = run_advisor(args.question, use_local_llm=not args.no_local_llm)
    print(
        json.dumps(
            {
                "answer": result.get("answer"),
                "recommendation": result.get("recommendation"),
                "synthesis_mode": result.get("synthesis_mode"),
                "evidence_count": len(result.get("evidence") or []),
                "llm_commentary_ok": bool((result.get("llm_commentary") or {}).get("ok")),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
