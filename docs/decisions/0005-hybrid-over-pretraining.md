# ADR-0005: Hybrid LLM+KG over pure KG-pretraining

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
We considered pivoting from "LLM + KG tools" to *training* a KG model (GNN/KGE via
edge ablation / node masking) as the hypothesis engine. Before investing, we
reviewed whether KG pretraining actually beats an LLM at link prediction /
hypothesis generation.

## Options considered
- **Pure KG-pretraining** (GNN/KGE link predictor replacing the heuristic scorer).
- **Pure LLM** (parametric knowledge).
- **Hybrid** (LLM orchestrates; KG grounds/verifies; optional trained KG model).

## Decision
Pursue the **hybrid** (LLM + KG), which also **regularizes hallucinations**. Defer
pure KG-pretraining; if pursued, use it as a calibrated *component* the LLM calls.

## Rationale & evidence (literature review)
- KG models beat *raw* LLMs on structured link prediction: **LORE (Brief.
  Bioinformatics 2025)** GPT-4o 31.7% MAP vs ML-ranker 90%; **TxGNN (Nat. Med.
  2024)** +49% AUPRC over BioBERT.
- But LLMs win **cold-start** (DR-SFT 0.80 vs TxGNN <0.30, bioRxiv 2026), and
  **hybrids beat both** (KG-FIT, FuseLinker, DrKGC).
- Benchmarks overstate the KG case: **hub/degree bias (PNAS 2025)** — a
  bias-only model beats sophisticated GNNs; "recover removed known edges" ≠
  novel discovery; no prospective head-to-head exists.

## Consequences
- Validates the architecture we were already building (LLM + KG grounding).
- Motivated ADR-0008 (KG-as-verifier) and ADR-0010 (honest calibration with a
  degree-preserving null — directly addressing the hub-bias caveat).
- A trained KG link-predictor remains an option, to be evaluated with time-sliced /
  degree-stratified / cold-start splits, not standard held-out MRR.
