# ADR-0040: Thinker-supplied critic verdict — Claude gates consensus, substrate stays LLM-free

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
Two paths reach shared consensus, and both embedded the **local** model (Qwen) as the critic:
`contribute()`'s literature gate calls `critic.criticize` (an LLM read of the abstract), and
`refine_hypothesis`'s loop calls it per bridge. But the critic is a **thinking task**, and the
project's architecture (ADR-0030/0031) says the *thinker* is the client's model (Claude), while
the *substrate* holds no LLM. So the arbiter of what the lab *believes* was the weakest model in
the stack — and, as the PTPN1↔JAK-STAT contribution showed, the local critic can accept a claim
while missing a material nuance (the regulation sign) that a stronger thinker catches.

The alternative "just set `LLM_BACKEND=anthropic`" routes *everything* to the cloud and breaks
the local-first privacy guarantee — too blunt.

## Decision
Let the **thinker supply the critic verdict**, keeping the substrate LLM-free, with the local
critic only as fallback:

- **`contribute(critic_verdict=...)`** — a verdict from the client's Claude (`'accept'`/`'reject'`
  or a dict) is used for the literature gate INSTEAD of running any local model. `_normalize_verdict`
  is **fail-closed** (anything not explicitly `accept` → `reject`). Every gate decision now logs
  **`critic_by`** ∈ {`thinker`, `local`, `provenance`} for attribution. Experiment findings still
  go through the deterministic provenance check (a substrate integrity invariant, not overridable).
- **`hypothesis_tools.refine_evidence(a, c)`** — the substrate half of the refinement loop, with
  **no generation**: for each KG bridge it returns the mechanism (incident predicates), the
  A–bridge–C PubMed triple count, and targeted abstracts. The thinker reads this, judges each
  bridge itself, and records confirmed links via `contribute(critic_verdict=...)`.
- **`refine_hypothesis(critic_fn=...)`** — the autonomous loop can take a thinker critic instead
  of the local one (default unchanged: local).
- **MCP**: `contribute_finding` gains `critic_verdict`/`critic_reason`; new shared tool
  `refine_evidence`. So a Claude MCP client does the whole gather → judge → record cycle, and the
  server never runs an LLM.

## Rationale & evidence
- **Consensus gated by the best available thinker.** The finding is judged by Claude (client),
  the local model is only a fallback — and the substrate stays a store, not a thinker (ADR-0030).
- **Fail-closed + attributable.** A malformed thinker verdict rejects rather than admits; `critic_by`
  makes every consensus decision auditable back to who (or what) judged it.
- **Independence preserved.** The gate is meant to be an *independent* reviewer; a fresh Claude
  reviewer distinct from the contributor supplies the verdict — the same separation the local
  critic provided, at higher quality.
- **Verified**: thinker `accept` → `pending_review` in **0.14 s** (no model call), logged
  `critic_by=thinker`; thinker `reject` → `rejected`; `_normalize_verdict` fail-closes `maybe`→`reject`.
  `refine_evidence` returns bridge mechanism + triple counts + abstracts with no LLM. MCP shared =
  **14 tools** (＋`refine_evidence`); all modules import clean.

## Consequences
- The last local-model dependency on the *consensus* path is removed — Claude can be the critic
  without `LLM_BACKEND=anthropic` and without sending everything to the cloud.
- The refinement loop is now decomposable: substrate gathers (`refine_evidence`), thinker judges,
  substrate records — exactly the mode-B pass done by hand for PTPN1, now first-class.
- The autonomous local `refine_hypothesis`/local critic remain for unattended runs (fallback).
