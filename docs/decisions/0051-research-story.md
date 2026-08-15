# ADR-0051: Research story — an honest narrative (not a highlight reel)

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
Third enjoyment lever after momentum (ADR-0049) and serendipity (ADR-0050): **narrative**. Turning
scattered runs + campaign lineage into a readable arc is good for morale and is a head start on the
paper's discussion. But a flattering story is worse than none — it breeds overclaiming, the exact
failure mode this whole substrate fights. The explicit design constraint (from the user): the story
must **interweave constructive criticism** — caveats and concrete ways to solidify each finding.

## Decision
Add **`research_story.py`** — a read-only narrative over `hypotheses/`, `reports/`,
`experiments/*/validity.json`, `campaigns/`, that, per step, weaves together:

- **Went well** — carried to an evaluated verdict, an honest null recorded, a validity gate that
  caught a real anomaly, a replication arm.
- **Verdict** — quoted from the evaluator's own words (the report's Verdict section).
- **Where it's shaky (caveats)** — derived from *real signals*, not manufactured: failed validity
  gates (halt = invalid-not-negative; flag = read-with-caveat), weak/novel-unverified grounding,
  already-published core (validation not discovery), `min_runs < 3`, **synthetic-vs-real data**,
  and the evaluator's own limitation sentences (underpowered / binding-limitation / did-not-
  replicate / no-gene-reaches).
- **To solidify** — the concrete action mapped to each caveat (power the cohort, replicate,
  confirm on real data, widen the panel, get independent corroboration…).

It closes on **the honest bottom line**: names the arc's *weakest link* and the single
highest-value move to solidify it. Exposed as the MCP shared tool `research_story(campaign)` and a
CLI (`python research_story.py [campaign]`).

## Rationale & evidence
- **Honest by construction.** Caveats come from the structured artifacts (validity gates, YAML
  data source, grounding/novelty, min_runs) and the evaluator's *own* words — the story can't be
  more flattering than the evidence. The closing "weakest link" makes the criticism unavoidable.
- **Woven, not bolted on.** Each step is "you did X (well) → verdict → **but** (caveat) → to
  solidify (action)", so praise and critique sit together rather than in a praise block.
- **Reuses the whole honesty stack.** It surfaces the same signals the substrate already computes
  (gates, power-aware nulls, novel≠true, synthetic vs real), turned into prose.
- **Verified on the real arc**: H001 correctly flags **SYNTHETIC data — the pipeline is validated,
  the biological claim is not** → *confirm on real data*; H002 (real) does **not** get that caveat,
  but does surface its **data_scale flag (observed_max 59.24)**, the evaluator's *"consistently
  negative but underpowered"* and *"binding limitation is power"* → power analysis + resolve the
  flag; the bottom line names H002 the weakest link (5 caveats). A tightened keyword set removed
  tangential "power"/"single" matches; the solidify list prints actions, not caveat echoes.
  Campaign-scoping works; MCP shared = **26 tools** (＋`research_story`); imports clean.

## Consequences
- Researchers get a morale-and-paper-useful arc that is candid about what's shaky — narrative that
  *strengthens* rigor instead of eroding it.
- Follow-ups: let the thinker (Claude) enrich the skeleton into publication prose while keeping the
  substrate's caveats fixed; map hypotheses to their contributed edges to fold in corroboration
  status; and offer a per-researcher "your journey" cut once persona memory exists.
