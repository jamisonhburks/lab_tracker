# ADR-0016: Refinement loop — novelty-filtered curate+critic triage

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
ADR-0015 added a novelty flag and KG-constrained generation but left the loop
manual: novelty flags an unpublished bridge, and *separately* the curator + critic
can verify it — but nothing drove them together over a batch of bridges. The insight
(user framing): the cheap novelty count and the expensive literature+critic pass form
a cascade that refines what counts as "already known."

## Decision
`refine_hypothesis(a, c)` (agent.py): for each bridge the KG surfaces between A and C,

1. **novelty.classify** (a PubMed count) triages the bridge: `bridge_published` →
   already known, skip the expensive step;
2. for every un-known bridge, **curate_literature** runs a targeted A–bridge–C search
   and extracts associations into the curated KG;
3. **critic.criticize** re-reads the sources and counts source-supported accepts;
4. the bridge is labelled **known** / **supported (real link)** / **spurious /
   speculative**, and verified links persist to the curated KG — so next round they
   count as known. The loop closes.

## Rationale & evidence
- **Cheap-filter → expensive-verify cascade**: novelty (one count) decides *which*
  bridges are worth the PubMed+LLM spend; the critic decides *whether they're real*.
  Neither alone can call "already known" — together they can.
- **Verified end-to-end** (demo KG, live PubMed + Qwen3-14B) on AF↔ischemic stroke:
  `warfarin` → curated 3, critic accepted 3 → *supported — real link*; `KCNQ1` (a
  synthetic demo edge) → no literature support → *speculative*. The expensive pass
  even **corrected a flaky novelty count** (warfarin's triple query transiently failed
  → mislabelled novel; curate+critic confirmed it real) — the cascade is robust to a
  bad cheap signal.
- **Two hardening fixes the run exposed**: (a) a failed PubMed count (`-1`) is now a
  distinct `unknown_bridge` status, never faked as a real zero; (b) `_pubmed_count`
  retries with backoff, since keyless NCBI throttles to ~3 req/sec and rapid counts
  were degrading to `-1`.
- **Novel ≠ correct** stays central: the loop's whole point is that a
  novelty-flagged bridge is a *candidate*, promoted only if the critic finds real,
  source-supported evidence.

## Consequences
- Rediscovery vs candidate-discovery vs spurious is now an automated triage, not a
  manual read.
- Expensive by design (bounded by `max_bridges` × `max_papers`); documented as such.
- The curated KG grows with verified links, compounding across runs.
