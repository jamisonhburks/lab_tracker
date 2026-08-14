# ADR-0044: Semantic grouping + one-step cluster→hypothesis

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The exploratory lane (ADR-0043) grouped misc findings by **exact** lowercased entity string and
drafted hypotheses only from a *session's* notes. Two gaps: (1) synonymous entities didn't
cluster — `IL8`/`CXCL8`, `myocardial infarction`/`acute myocardial infarction`, `type 2 diabetes`
/`… mellitus` were treated as unrelated, fragmenting real themes; (2) a promising cluster still
had to be formalized by hand, not handed straight to the retroactive-hypothesis drafter.

## Decision
- **Semantic grouping, two layers.** `_canon_key(entity)` keys each entity by its **KG node id**
  when it resolves (gene aliases via `gene_norm`, disease synonyms via `_resolve` /
  `ENTITY_NORM=semantic`), so ontology synonyms collapse to one key. On top, `_semantic_merge`
  adds a **precision-first embedding pass** (nomic-embed-text, cosine ≥ `_SEM_THRESHOLD` 0.80)
  for OFF-graph *surface variants* the KG can't resolve — graceful (identity map if the embedder
  is down). `group_misc` clusters over the merged keys; the two layers are complementary (KG =
  ontology synonyms, embedding = near-duplicate phrasings).
- **One-step cluster → hypothesis.** A shared `hypothesis_stub(entities, methods, observations)`
  builder now backs BOTH `session_journal.formalize_retroactively()` and the new
  `misc_research.formalize_group(theme)` — so a misc cluster drafts a hypothesis in the *same*
  format a session does. `group_misc` output points at `formalize_group(N)`, and MCP exposes
  `formalize_misc_group`.

## Rationale & evidence
- **KG normalization is the right primary layer.** The project already links entities
  ontologically (HGNC, KG names, BioLORD when enabled); keying groups by canonical id reuses that
  and is deterministic. The embedding pass is a *bonus*, deliberately conservative because
  nomic-embed-text is a general (not biomedical) embedder.
- **Calibrated the threshold, didn't guess.** Measured cosines: near-duplicates 0.95
  (`type 2 diabetes`/`… mellitus`), true synonyms 0.69–0.73 (`heart attack`/`MI`), unrelated
  0.37–0.46. So 0.80 merges surface variants safely without collapsing distinct diseases; real
  ontology synonyms are left to the KG layer (honest about nomic's limits).
- **Verified**: `_semantic_merge` collapses `myocardial infarction`→`acute myocardial infarction`,
  leaves `banana bread`; two findings with *different* subjects cluster into one theme purely via
  the merged synonym, while the unrelated study stays separate. `formalize_group(1)` drafts a
  hypothesis stub from the cluster (entities/methods/observations); `session_journal` uses the same
  builder. Shared MCP = 19 tools (＋`formalize_misc_group`); all modules import clean.

## Consequences
- Scattered analyses that used different names for the same thing now cluster, and a cluster
  becomes a draft hypothesis in one call — tightening the exploratory → shared-WIP path.
- The embedding merge is intentionally weak-but-safe; enabling `ENTITY_NORM=semantic` (BioLORD)
  upgrades the *KG* layer to catch true synonyms properly, which is the better lever than lowering
  the nomic threshold.
