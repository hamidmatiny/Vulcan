# ADR 014 — LangGraph advisor non-fabrication scope

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 22 (`advisor/`)

## Context

The v1.2.0 roadmap includes a LangGraph “advisor.” The failure mode is keyword
coverage: a chatbot that wraps a paid LLM API and invents backend rankings or
`$`/latency figures. That would contradict Vulcan’s honesty bar —
[ADR-007](./007-advanced-gpu-serving-techniques-scope.md) already forbids
**inventing GPU performance numbers**; the advisor must not invent *anything*
(backends, latencies, costs, routing outcomes).

## Decision

1. **Tool-grounded graph only.** `advisor/` is a small LangGraph with nodes
   that call **real repo data sources**:
   - `query_prometheus` → PromQL against local Prometheus (`:9008`), same query
     family as `observability/scripts/ci_smoke.sh`
   - `read_benchmark_results` → `benchmark/results/*-cpu.json` (schema-validated)
   - `query_routing_history` → live `POST /v1/infer` on the gateway; read the
     returned `routing` object (same surface `gateway/scripts/ci_fallback.sh`
     asserts)
   - `recommend` → synthesize using those tool results only
2. **Non-fabrication rule (extends ADR-007 by name).** Every numeric value and
   backend name in the final `answer` string **must** appear in the evidence bag
   collected from tool calls in that same run. CI enforces this with an exact
   grounding check (not exit-0, not fuzzy match) — analogous to phase-19’s
   logits-delta proof that the adapter is not a no-op.
3. **No new external LLM dependency.** Synthesis uses the repo’s pinned
   `reference-tiny-llm` (`models/artifacts/llm/gpt2-small/`) for an optional
   local commentary pass, plus a **template** that fills real retrieved values
   (the template is the CI-asserted answer). GPT-2-small prose quality is
   **explicitly not** what is being proven. Hosted Anthropic/OpenAI modes are
   manual opt-in only — see [advisor hosted LLM runbook](../runbooks/advisor-hosted-llm.md);
   never a CI default.
4. **CPU-only, local compose.** Prometheus, gateway, and the pinned model are
   local. No Anthropic/OpenAI/network LLM in CI.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Chatbot over a paid API with “context files” | Easy to hallucinate numbers; new API key; fails ADR-007 spirit |
| Mocked Prometheus / invented routing JSON in CI | Violates “real tool → real data”; would greenwash the proof |
| Proving fluent prose in CI | Wrong bar; GPT-2-small is for offline CPU, not quality |

## Consequences

- `check-adr-gate.sh` maps `advisor/**` → this ADR.
- No new host port required (CLI/library graph; no HTTP wrapper in phase 22).
- Operators get an explainable recommendation trail; demos stay honest.

## Compliance

- CI job runs the full graph against live local Prometheus + gateway and fails
  if any answer number/backend is not in that run’s tool evidence.
- Never add `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` as required CI secrets.
