# ADR-0046: Deep-search distillation → primary KG (cache expensive sweeps)

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
When a member has Claude "dive deeper" — corroborate against the KG *and* run a broad online
literature search — that sweep is expensive (many PubMed fetches, lots of reading) and, today,
ephemeral: the harvested knowledge lives only in that one session. The next person asks a similar
question and repeats the whole search. We want a deep search's knowledge to be **distilled into
the primary KG with provenance and the topic cached**, so future queries corroborate against the
now-enriched KG instead of re-running the sweep.

## Decision
Add **`deep_search.py`** and three MCP shared tools, splitting the work along the usual line —
substrate does what needs no judgment, the thinker distills:

- **`search_status(topic, a, c)`** — BEFORE a big search, check whether it's already covered: a
  prior deep-search **cache** hit (`memory/search_cache.jsonl`) and/or enough existing curated
  edges touching the entities (`COVERAGE_MIN`). If covered → "corroborate against the KG; the
  fresh sweep is likely redundant." This is the anti-repeat gate.
- **`deep_fetch(topic, [variants])`** — a broad multi-query PubMed fetch (**no LLM**), deduped by
  PMID, returning a corpus of abstracts for the thinker to distill. The thinker supplies the query
  variants (its search strategy); the substrate just executes the fetches.
- **`record_distillation(topic, [assoc], pmids)`** — the thinker submits the distilled
  associations; each (subject/predicate/object + a source PMID; malformed/source-less ones
  skipped) is written to the **primary written KG** (`kg_writer`) with provenance and evidence,
  and a cache entry records the topic + entities + who searched + counts. Attributed via the
  shared deployment's `_caller()`; the append is locked (`store_lock`).

## Rationale & evidence
- **Substrate stays LLM-free.** Fetch, write, and cache carry no judgment; the *distillation*
  (reading abstracts → structured associations) is the thinker's job (Claude), consistent with
  ADR-0030/0040. This also means it works over the shared HTTP server with no model in it.
- **Literature-evidence layer, not consensus.** Distilled associations go into `kg_writer` (the
  accumulating, provenance-carrying, confidence-scored evidence KG that `curate_literature`
  already writes to) — queryable immediately via `query_curated_findings`/`ground_claim`. They are
  "the literature reports this," with PMIDs — *not* gated lab conclusions (that's `contribute()`).
  A light junk/rigor pre-check keeps malformed extractions out.
- **The cache is the payoff.** Once Bob deep-searches a topic, `search_status` reports it as
  covered for everyone, and the KG holds the edges — so the next person doesn't repeat the sweep.
  Lower likelihood *and* lower effort of another big online search, exactly as intended.
- **Verified**: status NOT-covered → `record_distillation` (2 written, 1 malformed skipped,
  attributed to `bob`, cached) → status flips to COVERED (cache hit, dated, attributed); the 2
  edges are in the primary KG and queryable. `deep_fetch` returns real PubMed papers. Shared MCP =
  **22 tools** (＋3); all modules import clean; `memory/` gitignored so the cache stays local.

## Consequences
- Deep searches now *compound* into shared knowledge instead of evaporating; the lab's KG grows
  from members' searches, and redundant sweeps shrink over time.
- `curate_literature` (the local agent's search→distill→write) is the autonomous analogue; it can
  call `search_status` first and target the primary KG via this path.
- Follow-ups: expire/refresh stale cache entries (literature moves); and let a highly-corroborated
  distilled edge graduate from the evidence layer into gated consensus via `contribute()`.
