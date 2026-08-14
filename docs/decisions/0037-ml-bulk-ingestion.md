# ADR-0037: Bulk method ingestion (Stage 4) — `ml_ingest.py` + `ml_full` backend

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
Stage 1 hand-curated 61 author-verified methods; Stage 2 (ADR-0036) broadened the bridge.
Neither scales the *number of methods* — the fused graph knows ~61 architectures, a fraction
of the field. Stage 4 adds breadth of methods by ingesting an external corpus, without
diluting the curated core's rigor.

The canonical bulk source is the **Papers-with-Code methods dump**. PwC was sunset in 2025 and
its media URL now 302-redirects to HuggingFace (verified: the "download" returns HTML, and
`production-media.paperswithcode.com` fails the TLS handshake). So — as with PrimeKG earlier
(ADR-0018 era) — the live source is effectively unavailable, and the design must degrade
gracefully rather than depend on it.

## Decision
Add **`ml_ingest.py`**, a source-agnostic bulk-ingestion pipeline, and a **`ml_full`** backend
that merges the bulk layer with the curated seed.

- **Epistemic step-down, made explicit.** Curated methods are author-VERIFIED (real arXiv
  first/last author, title-guarded). Bulk methods are paper-LINKED but NOT author-verified —
  name, category, year, paper, lineage only. Bulk edges are source-tagged `paperswithcode
  (bulk)`, kept in a SEPARATE seed (`seeds/ml_bulk.json`), and never overwrite curated nodes.
- **Live-with-fallback.** `build_bulk` tries the PwC dump through `net.py` (retries), verifies
  it is really gzip-JSON (not an HTML redirect), and on any failure falls back to a **vendored
  snapshot** (`seeds/pwc_methods_sample.json`, 43 real methods not in the curated set). The
  path taken is printed, never silent. `--url`/a mirror bulk-loads the full ~2k taxonomy.
- **Harmonize → dedup → guard → cap.** Records map to `ml_schema.Method`; DEDUP by name
  against the curated set (a bulk method never shadows a verified one); GUARD drops records
  with no name or no paper; CAP at `MAX_BULK=800` with the overflow logged (no silent truncation).
- **Merged at load.** `kg_memory.load_ml_full` (`KG_BACKEND=ml_full`) concatenates the curated
  fused seed and `ml_bulk.json`, dedups nodes (curated wins), and degrades to curated-only with
  a note if the bulk seed is absent.

## Rationale & evidence
- **Lineage is the payoff.** The vendored snapshot sets each bulk method's `derived_from` to
  its real parent, often a curated method — so bulk methods connect INTO the curated bridge.
  Verified: `find_paths(DETR ↔ ECG)` returns `DETR —derived_from→ Transformer —suited_to→ ECG`,
  crossing bulk → curated → biomedical, with both `paperswithcode (bulk)` and `methodological`
  sources shown. Grounding/trust can see which hop is uncurated.
- **No dilution.** Dedup by name means adding bulk can only extend, never overwrite, the
  verified core. Bulk carries no fabricated authorship — absence is honest, not a gap to fill.
- **Verified end-to-end.** Live fetch fails cleanly (TLS handshake / HTML-not-gzip) → vendored
  fallback → 43 methods, 0 collisions, 0 drops → `seeds/ml_bulk.json` (86 nodes / 75 edges).
  `KG_BACKEND=ml_full` loads 404 nodes / 494 edges, 104 METHOD nodes (61 curated + 43 bulk).

## Consequences
- The method space nearly doubles (61 → 104) and stays connected to the clinical bridge via
  lineage, while the trust split keeps curated vs bulk legible.
- Pointing the pipeline at any PwC-schema mirror scales it to the full taxonomy with no code
  change; the live PwC adapter is ready for when/if a mirror is used.
- Future: an area→node grouping and optional arXiv authorship-enrichment for bulk methods
  (promoting a bulk method to curated once verified) are natural follow-ups.
