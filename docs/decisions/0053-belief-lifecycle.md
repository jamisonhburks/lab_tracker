# ADR-0053: The belief lifecycle — belief as living state (updates, trajectory, contradictions)

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
`confidence.py` (ADR-0007) answers a **stateless** question: given an edge's accumulated
evidence, how strongly should we believe it *right now*? It is recomputed on every read
(`query_curated_findings`, `contribute`'s routing) and then discarded. That makes the
substrate a *calculator* of belief, not a *holder* of it. A lab brain is supposed to feel
alive — its knowledge should visibly **update**, carry a **history** of how it got where it
is, and **surface disagreement** rather than silently overwrite it. None of that existed:
there was no persisted "the lab currently believes X at 0.62", no record that a contribution
moved a belief, and a contradicting claim was routed to `pending_review` and then forgotten.

## Options considered
1. **Recompute-only (status quo).** Cheap, but belief never persists, never shows a delta,
   and conflicts leave no trace. Fails the "living knowledge" goal.
2. **A new probabilistic belief model** (Bayesian updates with learned priors). More
   principled in theory, but it would introduce a second, uncalibrated epistemics layer
   competing with `confidence.py`, and we have no labelled outcome set to calibrate it
   (that's the separate Tier-2 calibration audit). Too much surface for one PR.
3. **Make the existing projection stateful** (chosen). Keep `confidence.py` as the single
   source of epistemics; add a thin lifecycle layer that *persists* its output per edge,
   *diffs* it on each contribution, keeps an append-only *trajectory*, and records opposing
   claims in a *contradiction ledger*.

## Decision
Add `beliefs.py` — the belief **lifecycle**, layered on top of (not replacing) the scorer:

- **Persisted belief per edge** — `snapshot()` projects the current belief from the
  authoritative accumulated evidence in `kg_writer` plus the KG grounding prior (the exact
  projection `query_curated_findings` already renders). `current()` returns it as state.
- **Incremental revision** — `revise()` re-scores an edge after its evidence changes and
  records the **delta** ("0.95 → 0.97, +0.02, supported"). Hooked into `contribute()`'s
  `auto_merged` branch; the pre-write belief is captured so the first delta is accurate.
- **Belief trajectory** — an append-only `memory/belief_log.jsonl`; state is a fold over the
  log, so history is never rewritten. This is simultaneously the "updating knowledge" trail
  **and the provenance of the confidence itself** (why the lab believes it as strongly as it
  does).
- **Contradiction ledger** — when a contribution genuinely OPPOSES an established belief
  (a refutation of a `supported` edge, or support for a `refuted` one), `contribute()`'s
  `pending_review` branch opens a first-class, resolvable conflict in
  `memory/contradictions.jsonl` (both sides preserved). Corroborating evidence merely held
  for conservative review does **not** open a conflict.

Read/resolve surface over MCP (shared tier): `belief`, `belief_history`, `contradictions`,
`resolve_contradiction`; `query_curated_findings` now shows a live trend arrow.

## Rationale + evidence
- **No new epistemics, no drift.** Belief is still `confidence.score_association()` over the
  same evidence — the lifecycle only persists and diffs it. One source of truth for *how
  strongly* we believe; the new module owns *that it's remembered and how it moved*.
- **Consistent with the substrate ethos.** Event-sourced, append-only, `store_lock`-guarded —
  the same shared-safe, auditable design as the contribution log (ADR-0032). Nothing is
  overwritten; the trail is immutable.
- **Substrate records, thinker judges (ADR-0040).** The substrate detects and *stores* a
  contradiction; it never decides who's right. `resolve_conflict()` records a thinker's
  verdict (upheld | overturned | contested), attributed.
- **Verified end-to-end.** The hermetic self-demo shows a belief rise 0.54 → 0.89 → 0.95 as
  three independent sources accrue, with the trajectory attributed step by step; the
  integration test drives the real `contribute()` path and confirms auto-merge revision, a
  contradiction opening on a refutation, *no* spurious conflict on corroboration, and clean
  thinker resolution.

## Consequences
- The substrate now reads as a lab brain with **updating** edge/hypothesis/concept
  confidence, a queryable belief **history** (confidence provenance), and visible
  **disagreement** — the Tier-1 gaps from the lab-brain review.
- Two clean seams are left for the follow-on tiers: the belief trajectory is the substrate a
  **calibration audit** (Tier 2) needs to score predicted-vs-realized confidence, and
  `last_updated` on each belief is the hook for **temporal decay / "as of"** freshness.
- Belief is materialized lazily (first touch through the lifecycle); edges that entered via
  distillation but were never re-contributed are scored live on read via `snapshot()`, so
  nothing is lost — they simply have no *trajectory* until evidence next moves them.
