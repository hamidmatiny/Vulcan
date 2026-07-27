# Manual: hosted LLM mode for the advisor (not CI)

**Status:** optional demo only — never a CI default (ADR-014).

The default advisor synthesizes with a **template filled from tool evidence** plus
optional local `reference-tiny-llm` (GPT-2-small) commentary. That is enough to
prove non-fabrication offline.

If you want nicer prose for a live demo:

1. Keep the same tool nodes (`query_prometheus`, `read_benchmark_results`,
   `query_routing_history`) — do not skip them.
2. Replace only the commentary generator with a hosted model of your choice.
3. **Still** run `advisor.non_fabrication.assert_answer_grounded` on the final
   answer before showing it. If the hosted model invents a number, the check
   must fail and you must not display the answer.
4. Do not commit API keys; do not wire hosted mode into `.github/workflows`.

Same pattern as GPU benchmarks (`docs/benchmarks/`) and cloud DVC remotes:
manual, explicitly opt-in, labeled.
