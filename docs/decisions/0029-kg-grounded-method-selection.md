# ADR-0029: KG-grounded ML method selection (Stage 3)

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
`propose_experiment` recommended experimental methodology from a hardcoded `_DESIGNS` map
(predicate → study design / data / test). With the fused ML KG now holding real
method-selection knowledge (modality → suited architecture → loss → metric → caveat,
ADR-0027/0028), that selection should be a **graph traversal**, not a lookup — so it's
grounded, auditable, extensible, and honest about the epistemic trust split.

## Decision
Add **`method_select.recommend_methods(target)`** — traverses the fused ML seed:
`DataModality —suited_to← Architecture —used_for→ Task —evaluated_by→ Metric`,
`Architecture —trained_with→ Loss`, plus the modality's `has_caveat` and encoding
standards, and each architecture's real authorship/year. `target` is a modality *or* a
disease (resolved to its modalities). It respects the trust split (stable methodological
edges vs benchmark-relative low-trust), and is **backend-independent** (reads the ML seed
directly, works whatever `KG_BACKEND` is loaded).

Wired into `propose_experiment` (appends the ML section when an entity bridges to a
modality) and exposed as its own orchestrator tool. The biomedical `_DESIGNS` study-design
map **stays** — it's complementary (experimental design vs ML method choice), and turning
*it* into a traversal would need a study-design ontology (STATO/OBI — later).

## Rationale & evidence
- **Verified**: `ECG → Transformer (Vaswani 2017), loss focal, metric AUROC`. For
  `type 2 diabetes` the two EHR structures diverge — **event-based** (OMOP/MEDS, caveat
  irregular-sampling) → **Transformer + GRU (Kyunghyun Cho 2014)**; **tabular** (caveat
  aggregation-loss) → **XGBoost (Tianqi Chen 2016)**. Appended cleanly after the
  biomedical design essentials in `propose_experiment`.
- **Honest degradation**: a disease not yet bridged to a modality says so (the bridge is
  curated — Stage 2 expands it), rather than guessing.

## Consequences
- Method selection is now traversable/groundable/contributable (the shared-knowledge
  pipeline can accrue method findings), and time/authorship-aware.
- `propose_experiment` becomes an actual design tool spanning *both* biomedical study
  design and ML method choice, grounded in one KG.
- Next: Stage 2 (bridge breadth so more diseases/modalities resolve) and Stage 4 (bulk
  ingestion) increase coverage; the traversal itself doesn't change.
