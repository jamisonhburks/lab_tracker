# ADR-0003: Retrieval scorers — recency-decay, hybrid, MMR, threshold

- **Date:** 2026-08-11
- **Status:** Accepted

## Context
The naïve scorers (episodic = keyword overlap, semantic = single-vector cosine)
were too crude: no recency, no exact-term precision, no diversity, no floor.

## Options considered
BM25, recency decay, hybrid dense+sparse fusion (RRF), cross-encoder rerank,
MMR diversity, score thresholding, domain embeddings.

## Decision
- **Episodic**: keyword overlap × **recency-decay** (half-life 30 days) + a
  min-overlap **threshold**.
- **Semantic**: **hybrid** BM25 + dense via **Reciprocal Rank Fusion**, a
  similarity **threshold**, and **MMR** for diversity.

## Rationale & evidence
- Hybrid fusion matters for biomedicine: embeddings blur exact identifiers (gene
  symbols, PMIDs) that BM25 nails.
- MMR trades a little relevance for coverage — right for hypothesis generation
  (varied evidence, not five near-duplicates).
- Threshold (measured floor ≈ 0.55 on `nomic-embed-text`) lets recall honestly
  return "nothing relevant" instead of the nearest junk.

## Consequences
- Cross-encoder rerank and domain embeddings were noted as further upgrades.
- The same embed+cosine pattern was later reused for semantic entity normalization
  (ADR-0009).
