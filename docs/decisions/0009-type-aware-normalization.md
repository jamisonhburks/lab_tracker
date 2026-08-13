# ADR-0009: Type-aware entity normalization (HGNC + BioLORD)

- **Date:** 2026-08-13
- **Status:** Accepted (supersedes the lexical-only and semantic-only stages)

## Context
Extracted entity strings ("ulcerative colitis (UC)", "IL8", "CID11879209") must
map to canonical KG nodes so the curated KG dedups and grounds correctly.

## Options considered (built and measured in sequence)
- **Lexical** (B1): string cleaning + substring match. Handles surface variants;
  misses synonyms.
- **Semantic** (B1.5): BioLORD-2023 embeddings. **Measured:** great on
  disease/clinical synonyms (`heart attack → Myocardial infarction` 0.79;
  `Crohn disease → Crohn's disease` 0.99) but **fails on gene symbols**
  (`IL8 → IL16` at 0.95 — matched by surface shape, not gene identity).
- **Type-aware** (B1.6): route each entity class to the right tool.

## Decision
A **type-aware cascade** in `normalize_entity`:
1. **Genes** → curated **HGNC** alias table (dictionary): `IL8 → CXCL8`,
   `HER2 → ERBB2`, `p53 → TP53` — deterministic, offline.
2. **Rest** → semantic (BioLORD, opt-in) else lexical.

## Rationale & evidence
- Gene symbols are *identifiers with official synonym registries* — a curated
  table (HGNC lists previous/alias symbols) beats any embedding. `IL8` is HGNC's
  *previous symbol* for CXCL8.
- Diseases are paraphrase-heavy → embeddings win.
- Different entity classes genuinely need different tools; no single method is best.

## Consequences
- `gene_norm.py` (HGNC), `entity_norm.py` (BioLORD, opt-in via `ENTITY_NORM`), and
  a graceful cascade in `kg_memory.normalize_entity`.
- Residual: junk ids can still semantic-match a gene above threshold — the critic
  agent or an id-filter is the follow-up. True concept normalization to
  UMLS/MONDO (not just Hetionet's node set) is a further step.
