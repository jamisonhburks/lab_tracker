# ADR-0060: Token-usage accounting — activity × outcome, with emergent-label discovery

- **Date:** 2026-08-17
- **Status:** Accepted

## Context
"How many tokens did we spend" is the wrong audit question for a research lab. The useful one is
*where did they go, and how much was wasted* — so a PI can see that a third of literature-review
spend was re-fetching what memory already held, or that planning is thrashing on retries. Answering
that needs per-call attribution, and it needs to cover **all** paid usage (the local Qwen
orchestrator is cost-free, but the Claude specialist and any frontier calls are real money —
ADR-0023's local↔frontier asymmetry).

Before this, spend was invisible: `llm.py` discarded the token counts both providers already return
(Ollama `prompt_eval_count`/`eval_count`; Anthropic `.usage`), and `scaling.py` could only estimate
artifact bytes.

## Decision
Add `token_meter.py` (capture + taxonomy), `label_discovery.py` (emergent labels), and
`token_audit.py` (rollup CLI). Two orthogonal labels per LLM call, because waste lives in the second:

- **ACTIVITY** — what the tokens did: `lit_search`, `kg_traversal`, `file_nav`, `memory_recall`,
  `hypothesis_gen`, `evidence_assess`, `planning`, `interpretation`, `code_impl`, `experiment_run`,
  `writing`, `critique`, `novelty_check`, `normalization`, `bookkeeping`.
- **OUTCOME** — whether it advanced the work: `productive` | `retry` | `redundant` | `dead_end` |
  `speculative` | `unknown`. `WASTE_OUTCOMES = {retry, redundant, dead_end}` (`speculative` is
  open-ended by design — serendipity — and is *not* counted as waste).

### Capture is central and always-on
Capture lives at the provider adapter (`llm.py` → `token_meter.on_llm_call`), so the agent loop, the
Claude specialist, tool-internal calls, and standalone experiments are all metered with no per-call
wiring. A process-global meter always accumulates; `flush()` persists JSONL to
`memory/token_ledgers/` (gitignored). Attribution comes from `contextvars` the caller sets:
`activity(label, outcome, provisional, hint)` and `run(run_id, layer)`. The agent wraps its
orchestrator turn as `planning`, each tool dispatch as the tool's activity, and consolidation as
`interpretation`; `llm.parse` marks re-asks after a bad parse as `retry`.

### Covering ALL paid tokens
Anything routed through `llm.py` is metered. Paid tokens that bypass the adapter — harness
subagents, batch jobs, the frontier judge in experiments — are logged with
`record_external(...)`, so nothing paid escapes the audit. A `layer` tag
(`orchestrator | specialist | external`) separates where the money actually goes.

### Local is counted, not free-of-record
Local Ollama tokens are **counted** but priced at **$0** — cost-free, not effort-free. So both
"paid $ by activity" and "total effort by activity" are answerable. Prices are editable list-price
estimates (`set_prices`); unknown models price at $0 rather than guessing.

### Provisional labels + emergent-label discovery
When the activity can't be confidently resolved (an unknown tool/specialist skill), the call is NOT
dumped into `uncategorized` — it is flagged **provisional** with a semantic `hint` (the tool/skill
name). `label_discovery.discover()` clusters provisional hints (token-overlap single-linkage, the
repo's concept-form style — no embeddings) **across a person's runs and across users when ledgers
are pooled**, surfacing candidate NEW activity labels. A cluster recurring across several distinct
sources is a stronger candidate; adopt the good ones into `TOOL_ACTIVITY`.

## Consequences
- `token_audit.py` reports tokens/$ by activity, by layer, an activity×outcome waste table, and
  `--discover` candidate labels. `memory/token_ledgers/` is the durable source; the per-run copy in
  each tool ledger (`spend`) is co-location convenience and is not double-counted by the audit.
- Telemetry is best-effort and must never break a run (observer/flush exceptions are swallowed).
- Waste signals wired so far: `retry` (bad-parse re-asks in `llm.parse`); `redundant`
  (`curate_literature` extraction when `deep_search.search_status` says the topic was already
  covered); `dead_end` (`refine_hypothesis` verification of a pair `deadends.check` flags as an
  *evidenced* dead end). Nested tags respect precedence via `current_outcome()` — a `dead_end`
  block is never downgraded to `redundant`.
- Honesty caveats: outcome still defaults to `productive`, so measured waste is a *lower bound* —
  only the paths above are instrumented; other redundant/dead-end work reads as productive until
  its module tags it. Dollar figures are estimates — **token counts are the load-bearing signal**.
- Experiments opt in by calling `token_meter.enable_autoflush()`; without it their local (cost-free)
  spend is captured in-memory but not persisted.

## Alternatives considered
- **Tool-level counting** (attribute spend to the tool row in `tool_ledger`) — rejected: spend
  happens at the LLM call, and one tool can make many calls; contextvars attribute correctly with
  far less wiring.
- **Force every unknown into `uncategorized`** — rejected: hides emerging kinds of work. The
  provisional+discovery path lets the taxonomy grow from real usage instead of being frozen.
