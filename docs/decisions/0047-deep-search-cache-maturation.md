# ADR-0047: Mature the deep-search cache — expiry, graduation, curate integration

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
ADR-0046 made a deep search distil into the primary KG and cache the topic. Three gaps kept it
from being trustworthy day to day: (1) the cache never expired, so a topic searched a year ago
looked as fresh as one searched today — but the literature moves; (2) distilled edges accumulated
evidence in the evidence layer but had no path *up* to gated consensus once well-corroborated;
(3) the local agent's own `curate_literature` didn't consult the cache, so it happily repeated
sweeps the lab had already done.

## Decision
- **Expiry / refresh** — `STALE_AFTER_DAYS` (180). `search_status` computes the age of the most
  recent cache hit; past the threshold it reports **COVERED BUT STALE** and recommends a refresh
  (`deep_fetch` biased to recent papers → `record_distillation`; evidence dedups, so re-distilling
  is cheap and updates the cache). Fresh hits still say "covered → skip the sweep."
- **Graduation** — `graduation_candidates(min_sources)` lists curated/distilled edges backed by
  ≥ N **independent** sources that aren't in the consensus pipeline yet; `graduate(s, p, o,
  critic_verdict)` routes such an edge from the literature-EVIDENCE layer into GATED consensus via
  `contribute()`. Well-corroborated edges thus have a path to "what the lab believes."
- **`curate_literature` integration** — the local agent now calls `search_status` first (surfacing
  prior coverage) and `mark_searched` after, so its curation lands in the shared cache and it flags
  when it's re-covering trodden ground (it still curates — evidence dedups + refreshes).

## Rationale & evidence
- **Staleness is honest.** A cache is only useful if it knows when it's out of date; flagging
  rather than silently trusting an old sweep matches the rest of the substrate's "novel ≠ false,
  absence ≠ refutation" candor.
- **Graduation reuses the gate.** It doesn't invent a new consensus path — it feeds a corroborated
  edge through `contribute()`'s existing critic gate + conservative routing. Observed (and
  acceptable): a strongly-corroborated edge tends to **auto-merge** — it has *earned* the
  confidence — while a borderline one would route to peer review. That's the intended gradient.
- **One shared cache.** `mark_searched` shares a single append helper with `record_distillation`,
  so the local agent and the MCP deep-search tools write the same cache — the lab has one view of
  "what's been searched."
- **Verified**: a 957-day-old hit is flagged STALE with a refresh recommendation; a 3-source edge
  surfaces as a graduation candidate, `graduate()` merges it (attributed) and it then drops off the
  candidate list (already contributed); `curate_literature` imports + records. Shared MCP = **24
  tools** (＋`graduation_candidates`, `graduate`); all modules import clean.

## Consequences
- The deep-search cache is now a living index: it ages out, feeds corroborated knowledge up into
  consensus, and is fed by *both* the interactive deep-search tools and the local agent's curation.
- The single `kg_writer` store holds evidence-layer and auto-merged consensus edges together;
  `_consensus_status` scores by accumulated evidence, which is why a well-corroborated graduation
  auto-merges. A future split (separate evidence vs consensus stores) would make the tiering even
  crisper, if it's ever worth the complexity.
- Follow-up: a scheduled refresh that re-runs stale topics, and per-source independence checks
  (distinct labs/journals) so "3 sources" can't be gamed by one group citing itself.
