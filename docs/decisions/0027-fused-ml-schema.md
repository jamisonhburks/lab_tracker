# ADR-0027: Fused ML+biomedical schema — methods as a distinct epistemic class

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The lab does biomedical *and* ML/AI research. We want one KG where a clinical question can
be reasoned through to an ML method ("which architecture/loss for this modality?"). But
methods are **epistemically different from phenomena**: a gene→disease edge is *discovered*
(author-independent, stationary, true/false), whereas a method edge (Transformer `used_for`
translation; RoBERTa `outperforms` BERT) is a property of a *created artifact* —
author-attributed, time-indexed, benchmark-relative/non-stationary, effective-in-context
rather than true. A naïve "just add ML triples" would erase that distinction.

## Decision
Add **`ml_schema.py`** — the ML/method layer, built around that epistemic difference, and a
**`KG_BACKEND=ml_demo`** fused graph. Beyond the obvious method↔task↔modality edges it adds:
- **Authorship + institution**: `first_author` / `last_author` / `from_lab` + a
  `Publication` node with a **year** (methods are *dated* artifacts — the year is
  load-bearing for non-stationarity).
- **Lineage**: `derived_from` (parent) and `superseded_by` (successor).
- **An epistemic classification of edges** (`classify_edge`): `method_artifact`,
  `method_claim_stable` (`suited_to`/`trained_with`/`used_for` — higher trust), and
  `method_claim_benchmark` (`achieves`/`outperforms` — LOW trust). Benchmark edges carry a
  `benchmark:` source, and `benchmark`/`leaderboard`/`sota` were added to `_LOW_TRUST`, so
  paths leaning on "X is SOTA" ground as **weak** — SOTA churns like the alpha-decay noted
  in the trading aside.
- **The bridge**: `Disease —manifests_in→ DataModality —suited_to← Architecture`, so a
  single traversal crosses domains.

Emitted in kg_memory's `id/name/category` + `subject/predicate/object/source` shape, so the
existing traversal/DWPC/calibration/grounding code works unchanged (as with Monarch).

## Rationale & evidence
- **Verified on `ml_demo`** (27 nodes / 27 edges): cross-domain path `atrial fibrillation →
  ECG → Transformer`; lineage `RoBERTa → BERT → Transformer`; Transformer carries its
  authorship/lab/intro-paper; and the trust split is real — `1D-CNN suited_to ECG` grounds
  as `grounded` while `RoBERTa achieves GLUE` grounds as `weakly_grounded`.
- **Reuses, doesn't reinvent**: the reified-evidence, `_LOW_TRUST` grounding, DWPC
  degree-weighting (Lab/Metric hubs are correctly discounted), and confidence machinery all
  apply to method edges as-is.

## Caveats & consequences
- **Last-author-as-PI is a *biomedical* convention** — ML/CS author order is noisier
  (contribution order, equal-contribution), so `last_author` is captured as *data*, not read
  as "senior". Authorship in the seed is illustrative; a real build populates it from
  Semantic Scholar / DBLP / Papers-With-Code (+ AI-KG for method↔task↔metric, CSO for the
  topic backbone, EDAM/OBI/STATO for the biomedical-method bridge).
- `propose_experiment`'s hardcoded `_DESIGNS` map can now become a KG *traversal* (method
  selection grounded in the graph), and the shared-knowledge pipeline can accrue *method*
  findings ("Transformer-for-ECG worked/didn't") with the same power-weighting.
