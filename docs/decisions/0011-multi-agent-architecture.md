# ADR-0011: Orchestrator + specialists; separation of concerns

- **Date:** 2026-08-13
- **Status:** Accepted (direction); first specialist built

## Context
The single agent ("brain") synthesizes info and generates hypotheses. A full
research system needs other agent classes it can deploy (scraper, synthesizer, KG
curator, critic, experiment designer, implementer, runner, evaluator).

## Options considered
- One monolithic agent doing everything.
- **Orchestrator + specialist agents**, each its own prompt/tools/model.

## Decision
Adopt the **orchestrator + specialists** pattern (`docs/agent-architecture.md`),
with a load-bearing rule: **separate generate / execute / interpret** into
distinct agents. Build the **synthesizer → KG-curator** first.

## Rationale & evidence
- Separation of concerns prevents **self-confirmation** — one agent that
  generates, runs, *and* judges rationalizes its own hypothesis into "confirmed."
  Adversarial-by-construction (mirrors the project's `CLAUDE.md` agent roles:
  runner ≠ interpreter, evaluator ≠ re-runner).
- Prior art: AI co-scientist, AI Scientist, SciAgents, ResearchAgent.
- The synthesizer→curator was highest-leverage: it grows the KG the brain grounds
  on and feeds the confidence scorer real evidence — closing the literature→KG loop.
- Honest caveat: the literature/hypothesis half is mature; **autonomous execution**
  (implementer→runner→evaluator) is the hard, less-proven half and needs a human in
  the loop, especially with clinical data.

## Consequences
- `kg_writer.py` (curator) + `curate_literature` / `query_curated_kg`. The
  compute-heavy **runner** is what a cluster is actually for. Critic agent is the
  recommended next specialist.
