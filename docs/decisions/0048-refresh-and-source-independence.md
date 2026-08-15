# ADR-0048: Scheduled cache refresh + source-independence for graduation

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
Two follow-ups from ADR-0047 mattered enough to build. (1) The cache *flags* staleness but nothing
acts on it — a stale topic stays stale until someone happens to re-ask. (2) Graduation to consensus
counted **distinct** sources, which one group can game by citing its own papers (3 PMIDs from the
same lab is not 3 independent corroborations). If graduation is going to gate what the lab
believes, the count has to mean *independent*.

## Decision
- **Scheduled refresh** — `deep_search.stale_topics(older_than)` returns topics whose most-recent
  cache entry is past the threshold. `refresh_stale.py` (cron on the cluster) re-runs the local
  agent's `curate_literature` on each, re-distilling fresh evidence into the primary KG and writing
  a new cache entry (which resets staleness). It's autonomous, so it uses the local model — run it
  where the model lives. The MCP `stale_topics` tool surfaces the same list to any session; a
  `--dry-run` lists without acting.
- **Source independence** — `deep_search.independent_count(sources)` groups PMIDs by **last author**
  (same group → one independent source), plus each distinct non-PMID source and each unresolvable
  PMID. PMID→last-author metadata is fetched from PubMed once and **persisted** (`memory/pmid_meta
  .json`), so the check is cheap after first use. `graduation_candidates` / `graduate` now require
  ≥ N **independent** sources, with a cheap distinct-source pre-filter so the network check runs
  only on the handful of edges that could qualify.

## Rationale & evidence
- **Freshness needs an actor, not just a flag.** A cron re-distil keeps the KG current without a
  human in the loop; it reuses the existing autonomous pipeline (`curate_literature`) rather than
  inventing a new one, and each refresh naturally resets the topic's staleness via `mark_searched`.
- **Independence is the honest bar for consensus.** Grouping by last author directly targets the
  "one group citing itself" failure mode. It's conservative where it can't resolve metadata
  (counts unresolved PMIDs individually rather than merging them wrongly), and graceful (falls back
  to distinct-source count if PubMed is unreachable).
- **Cheap by construction.** The distinct-source pre-filter means independence (network) is
  computed only for edges already past the raw threshold; the persisted meta cache means each PMID
  is resolved once.
- **Verified**: `stale_topics` picks the most-recent entry per topic (957-day `IL6 AF` stale, a
  recent topic not); `independent_count` scores 3 PMIDs with 2 shared last-authors as **2** (and
  +1 for a non-PMID source); graduation of that edge is **rejected at min=3** but accepted at min=2
  — the anti-gaming behavior. `refresh_stale.py --dry-run` runs without the model; MCP shared =
  **25 tools** (＋`stale_topics`); all modules import clean.

## Consequences
- The deep-search cache now self-heals (scheduled refresh) and graduation to consensus is
  gameable-resistant (independent-source bar) — the two things needed before graduation can gate
  lab belief.
- Independence is author-group-based; it won't catch collusion across labs or distinguish a genuine
  multi-site replication from a large consortium reusing one senior author. Journal/affiliation-
  level independence (or an explicit replication flag) is the natural next refinement.
- The refresh job depends on the local model; a lab running the shared server LLM-free must point
  the cron at a model host (local Qwen or `LLM_BACKEND=anthropic`).
