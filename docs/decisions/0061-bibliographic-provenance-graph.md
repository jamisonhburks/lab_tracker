# ADR-0061: Bibliographic / provenance graph — Work nodes keyed by persistent IDs

- **Date:** 2026-08-17
- **Status:** Accepted

## Context
Literature handling had three gaps that make provenance imprecise and effort redundant:

1. **Dedup is topic-level, not paper-level.** `deep_search` caches searched *topics*
   (`search_cache.jsonl`, `search_status`/`mark_searched`). The same paper surfaced by two topics
   is re-fetched and re-extracted — wasted tokens (exactly the `redundant` signal ADR-0060 tags).
2. **Papers are PMID-only, abstract-only.** Fetching is raw PubMed EUtils `AbstractText`. There is
   no DOI, no cross-ID resolution, and no notion of whether we read the *abstract* or the *full
   text* — so evidence strength can't distinguish a title/abstract skim from a full-paper read.
3. **Sources are opaque strings.** KG edges carry `source: "PMID:123"`. A source is not a
   first-class node, so "which paper, read how deeply, and what else does it support/cite?" is
   unanswerable and `provenance.py` can only reconstruct per-experiment cards.

## Decision
Add `biblio.py`: a **separate bibliographic/provenance graph** — a third graph layer beside the
domain KG (`kg_memory`) and the ML KG, consistent with the pluggable multi-graph design. Nodes are
**Works** (papers, later datasets) keyed by a **persistent ID**, canonical key preferring
`doi:` → `pmid:` → `pmcid:`, with a crosswalk so any known id resolves to the same Work.

A Work records:
- **xrefs** — doi / pmid / pmcid / openalex (crosswalk);
- **access** — `none < abstract < full_text` (+ `text_source`, `retrieved_at`); upgrades monotonically;
- **coverage** — `[{lab_query, contributor, ts}]` → **paper-level dedup** ("have we already ingested
  this exact paper, and how deeply", replacing topic-level "did we search this");
- **supports** — the association keys this Work is cited as evidence for → every domain edge's
  `source` becomes a link to a Work node, so support is precisely traceable.

### Sources — tiered, not all at once
- **Primary resolver: Europe PMC** *(implemented)*. Biomedical; gives abstracts **+ full text for
  OA** and native PMID↔PMCID↔DOI crosswalk — the drop-in upgrade from raw EUtils that also fills the
  access axis. `resolve_europepmc` (crosswalk/enrich) + `_fetch_fulltext_europepmc` (full text).
- **OA access signal: Unpaywall** *(implemented)* — `resolve_unpaywall`/`oa_status` (needs a contact
  email) to flag OA + locate full text, sharpening `full_text`.
- **Citation edges: OpenCitations** *(implemented)* — `resolve_citations`/`fetch_citations` build
  Work —cites→ Work for support-*chain* tracing; resolver is injectable (OpenAlex can swap in).
- **Canonical metadata fallback: Crossref** — deferred (Europe PMC covers the biomedical corpus).
- **DataCite** — deferred; only when findings tie to datasets (GWAS/PRS provenance).
- **OpenAIRE** — deferred (heavy aggregator, low early value).
- **ORKG, ResearchGraph** — **not adopted.** ORKG overlaps our own abstract-extraction KG;
  ResearchGraph is largely subsumed by OpenAlex/OpenAIRE.

Licensing across the adopted set is open (mostly CC0 metadata), which suits the open-core posture.

## Consequences
- `biblio.py` is pure + best-effort: the registry logic (crosswalk, access upgrade, dedup, links) is
  offline and unit-tested; network resolvers (`resolve_europepmc`) sit behind `net.py`, are
  best-effort, and are stubbed in tests. The store is `memory/biblio/works.jsonl` (gitignored).
- `curate_literature` registers each paper as a Work (abstract access, tagged with the lab query)
  and links the associations it extracts to that Work — the source→claim payoff. `deep_search`
  dedup can consult `biblio.seen()` to skip re-ingesting a paper already read at ≥ the same depth.
- This reinforces the H003 thesis (the substrate is the value): a per-lab provenance graph where
  every claim is source-linked and access-audited is a moat, not plumbing.
- Honest caveat: full-text access is only asserted when a resolver confirms OA availability;
  absence of `full_text` means "not confirmed", not "closed".

## Alternatives considered
- **Extend the domain KG with paper nodes** — rejected: conflates bibliographic identity/coverage
  with biomedical semantics; a separate keyed layer keeps both clean and lets sources dedup across
  domains.
- **Adopt OpenAlex as the single backbone** — reasonable and kept as an alternative; Europe PMC wins
  as *primary* here purely because the lab is biomedical and already on PubMed, so full-text + ID
  crosswalk come for free with the smallest change.
