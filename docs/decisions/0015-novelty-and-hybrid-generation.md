# ADR-0015: Novelty flag + hybrid (KG-constrained) hypothesis generation

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
Two gaps surfaced while validating the T2D↔Alzheimer's run against the real
literature:

1. **The generation flow was KG-only.** `find_paths` / `assess_hypothesis` /
   `calibrate_link` are deterministic graph operations; the LLM only *orchestrated*
   and *narrated* them. The hybrid (ADR-0005) existed only in the *LLM→KG* direction
   (consolidate→ground, curate→critic). The *KG→LLM* direction — retrieve a subgraph,
   then have the model **reason over it** — was never built. So the system wasn't
   actually doing "both."

2. **The KG cannot tell novelty from rediscovery.** Every KG edge is drawn from the
   literature, so a surfaced link (e.g. T2D–APOE–AD) is, by construction, already
   published. The 20 "shared genes" it produced were real but *known* — the run was
   validation-of-method, not discovery. Nothing flagged which links were rediscovery
   vs a genuinely new juxtaposition (the Swanson move).

## Decision
- **`novelty.py` — `check_novelty(a, c, via=None)`**: PubMed co-mention counts
  classify a link. With a bridge gene, the **triple** A–G–C is judged (not the pair —
  a known comorbidity can still hide an unpublished mechanism): `bridge_published`
  (known mechanism) / `emerging_bridge` (lightly studied) / `novel_bridge` (candidate
  mechanism for a known link) / `novel_juxtaposition` (fully new).
- **`generate_hypothesis(a, c)` (agent.py) — the hybrid**: the KG enumerates the
  subgraph connecting A and C; the model synthesizes a mechanistic hypothesis
  **constrained to those paths** (may only build on intermediates that appear in the
  graph — this regularizes hallucination); the output is annotated with `check_connection`
  grounding + `check_novelty` on the most-central bridge. Both are first-class tools.

## Rationale & evidence
- **Hybrid verified** (Hetionet + Qwen3-14B): on T2D↔AD the model synthesized a
  mechanism using only subgraph genes (OGG1, SOD1, LEP, AKT1, INS, BCL2, PON1, APOE,
  CASP8 — no invented nodes), ranked **APOE "high"** centrality (correct — top AD
  gene), and self-labelled it a rediscovery via the novelty annotation.
- **Novelty flag independently reproduces the lit-agent's manual tiering**: IDE /
  IAPP / APOE → `bridge_published` (well-established); ND1 → `emerging_bridge` (weak);
  **CTF1 → `novel_bridge`** — the exact gene the literature critic flagged as likely
  spurious. Two independent methods (PubMed counts vs. an LLM lit review) agreeing is
  the signal. This is why the fix to judge on the **triple, not the pair** mattered:
  the coarse pair-level check masked CTF1 as "established."
- **Novel ≠ correct** (inverse of ADR-0008's closed-world humility): a `novel_bridge`
  can be a spurious indirect graph path. The flag is a *reason to check*, not a truth
  claim — it is one step in a refinement **loop**: KG surfaces bridges →
  `check_novelty` flags the unpublished ones → `curate_literature` on that specific
  target → `criticize_curated_kg` decides real-new vs spurious → the verdict refines
  what counts as "already known" for the next round.

## Consequences
- Real hypothesis *generation* (not just retrieval) now runs through the KG, with the
  graph as a regularizer against invented mechanisms.
- Novelty is explicit, so a run can separate rediscovery (validates the method) from
  candidate discovery (worth the literature+critic loop).
- **Next**: a thin orchestrator that runs the loop automatically for a batch of
  flagged `novel_bridge`/`emerging_bridge` targets (its own ADR/PR).
