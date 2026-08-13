# ADR-0023: Scaling profile — content per hypothesis, and `scaling.py`

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
With the loop closed (ADR-0020) and traced (ADR-0021/0022), the question is what it
*costs* to run a hypothesis end-to-end, and how that scales — so we can budget running
many. This ADR records the measured profile and adds a reusable accounting tool.

## Decision
Add **`scaling.py`** — content accounting per experiment (spec, code, metrics, figures,
log, report, provenance, ledger → bytes/lines/text-tokens + scientific-op count).
`python scaling.py` prints a cross-experiment table; `python scaling.py <id>` a
breakdown. Measures on-disk artifacts deterministically; the LLM-token axis is recorded
here from observed pipeline telemetry.

## The measured profile (H001 synthetic vs H002 real-data)
**On-disk artifacts:** H001 206 KB / 1,342 lines (~53k text-tokens); H002 369 KB / 3,809
lines (~94k). ~1.8× overall — but the **run log blew up 24×** (6 KB → 147 KB: real
experiments log every gene/model/fetch), and experiment **code 2.2×** (GEO fetch/parse/
collapse/covariate model).

**LLM orchestration (Claude subagent tokens):** H001 ~73k total (planner 8.5k /
implementer 17k / runner 21k / evaluator 27k); H002 ~218k (planner 27k / implementer 41k
/ runner 70k / evaluator 80k). **~3×.**

## The finding (why this matters)
- **Generation is token-free; testing is what you pay for.** The local Qwen orchestrator
  (KG generation, novelty, refinement) runs on-device at zero token cost. The ~73k–218k
  is entirely the **Claude** test/interpret pipeline.
- **The runner + evaluator dominate** (~65% of tokens) and scale hardest with data
  complexity — real data means iteration (e.g. the AD='AA' fix), power/replication
  analysis, and verbose logging. A hypothesis is **cheap to propose, expensive to test
  honestly**, and the multiplier lands exactly where rigor lives.
- **Scaling law:** cost ≈ `N × per-hypothesis Claude test cost` (~73k synthetic to
  ~220k real subagent tokens). 100 real-data hypotheses ≈ ~22M tokens.

## Consequences / levers
- `scaling.py` lets us profile content-per-hypothesis across all future experiments.
- Two optimisation levers if scaling to many: (1) trim per-gene run-log verbosity (the
  24× disk driver; already gitignored); (2) route the **mechanical runner** to a cheaper
  model while keeping the strong model for the **evaluator** (interpretation is where the
  honest-null quality is earned) — cutting the dominant cost without losing rigor.
